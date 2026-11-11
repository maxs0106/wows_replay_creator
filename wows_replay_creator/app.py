import json
import io
import shutil
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="WoWS Legends Replay Creator", page_icon="⚓", layout="wide")
st.markdown("""
<style>
.stApp {background:#0b131e;color:#e5e7eb}
section[data-testid="stSidebar"] {background:#070d14}
.block-container {padding-top:1.5rem}
h1,h2,h3 {color:#f8fafc}
</style>
""", unsafe_allow_html=True)

st.title("⚓ WoWS Legends Replay Creator")
st.caption("戦闘イベントデータから、マップ上の戦況リプレイを作成するWebアプリ")

st.warning(
    "重要：このアプリは現段階ではゲーム本来の .wowsreplay を生成・復号しません。"
    "暗号化されたリプレイからイベントを取り出すには、対応する復号仕様または解析済みデータが必要です。"
    "本アプリはJSON/CSVの戦闘イベントを読み込み、再生・分析・動画化するMVPです。"
)

REQUIRED = ["time", "player", "ship", "x", "y", "event"]
OPTIONAL = ["target", "damage", "team", "hp", "detail"]

def sample_data():
    rows = []
    ships = [
        ("Player_A", "Split", "Blue", 0, 0),
        ("Player_B", "Yamato", "Blue", -12, -8),
        ("Player_C", "Des Moines", "Red", 28, 18),
        ("Player_D", "Shimakaze", "Red", 18, -20),
    ]
    for t in range(0, 601, 10):
        for i, (player, ship, team, sx, sy) in enumerate(ships):
            x = sx + (t / 600) * (10 if team == "Blue" else -8) + i * 1.2
            y = sy + (t / 600) * (8 if i % 2 == 0 else -5)
            rows.append(dict(time=t, player=player, ship=ship, x=x, y=y,
                             event="position", target="", damage=0, team=team, hp=100,
                             detail="位置情報"))
    rows += [
        dict(time=125, player="Player_A", ship="Split", x=3, y=4, event="shot",
             target="Player_C", damage=0, team="Blue", hp=100, detail="主砲発射"),
        dict(time=128, player="Player_A", ship="Split", x=3, y=4, event="hit",
             target="Player_C", damage=4200, team="Blue", hp=82, detail="命中"),
        dict(time=240, player="Player_D", ship="Shimakaze", x=15, y=-17, event="torpedo_hit",
             target="Player_B", damage=9800, team="Red", hp=64, detail="魚雷命中"),
        dict(time=410, player="Player_B", ship="Yamato", x=-4, y=-2, event="sink",
             target="Player_D", damage=0, team="Blue", hp=0, detail="撃沈"),
    ]
    return pd.DataFrame(rows).sort_values("time")

def normalize(df):
    df = df.copy()
    for c in REQUIRED:
        if c not in df.columns:
            raise ValueError(f"必須列がありません: {c}")
    for c in OPTIONAL:
        if c not in df.columns:
            df[c] = ""
    df["time"] = pd.to_numeric(df["time"], errors="coerce")
    df["x"] = pd.to_numeric(df["x"], errors="coerce")
    df["y"] = pd.to_numeric(df["y"], errors="coerce")
    df["damage"] = pd.to_numeric(df["damage"], errors="coerce").fillna(0)
    df = df.dropna(subset=["time", "x", "y"])
    df["event"] = df["event"].astype(str).str.lower()
    return df.sort_values("time")

uploaded = st.sidebar.file_uploader("戦闘イベントを読み込む（JSON / CSV）", type=["json", "csv"])
if uploaded:
    try:
        if uploaded.name.lower().endswith(".csv"):
            source = pd.read_csv(uploaded)
        else:
            raw = json.load(uploaded)
            source = pd.DataFrame(raw["events"] if isinstance(raw, dict) else raw)
        df = normalize(source)
        st.sidebar.success(f"{len(df):,} 件のイベントを読み込みました")
    except Exception as e:
        st.sidebar.error(f"読み込みエラー: {e}")
        df = sample_data()
else:
    df = sample_data()
    st.sidebar.info("サンプルデータを表示中")

st.sidebar.download_button("イベント形式のサンプルJSON", json.dumps({"events": sample_data().to_dict("records")}, ensure_ascii=False, indent=2), "sample_events.json", "application/json")
st.sidebar.download_button("イベント形式のサンプルCSV", sample_data().to_csv(index=False).encode("utf-8-sig"), "sample_events.csv", "text/csv")

end_time = float(df["time"].max()) if len(df) else 0
if end_time <= 0: end_time = 1
st.subheader("リプレイ操作")
current = st.slider("再生位置（秒）", min_value=0.0, max_value=end_time, value=0.0, step=max(1.0, end_time/600))
speed = st.select_slider("再生速度", options=[0.25, 0.5, 1, 2, 4, 8], value=1)
visible = df[df.time <= current]
positions = visible[visible.event == "position"].sort_values("time").groupby("player", as_index=False).tail(1)
events_now = visible[visible.event != "position"]

c1,c2,c3,c4 = st.columns(4)
c1.metric("経過時間", f"{int(current)//60:02d}:{int(current)%60:02d}")
c2.metric("参加プレイヤー", df.player.nunique())
c3.metric("イベント数", len(visible))
c4.metric("累計ダメージ", f"{int(df.damage.sum()):,}")

left, right = st.columns([1.7, 1])
with left:
    st.subheader("戦況マップ")
    fig = go.Figure()
    for team, color in [("Blue", "#38bdf8"), ("Red", "#fb7185")]:
        sub = positions[positions.team.astype(str) == team] if "team" in positions else positions
        if len(sub):
            fig.add_trace(go.Scatter(x=sub.x, y=sub.y, mode="markers+text",
                text=sub.player, textposition="top center", name=team,
                marker=dict(size=15, color=color, line=dict(width=1, color="white")),
                customdata=sub[["ship","hp"]].astype(str),
                hovertemplate="%{text}<br>%{customdata[0]}<br>HP: %{customdata[1]}<extra></extra>"))
    # Draw shot/hit indicators at their event coordinates
    for _, e in events_now.iterrows():
        symbol = "x" if e.event in ("shot", "torpedo") else "star"
        color = "#fbbf24" if e.event in ("shot", "torpedo") else "#a3e635"
        fig.add_trace(go.Scatter(x=[e.x], y=[e.y], mode="markers",
            marker=dict(symbol=symbol, size=13, color=color),
            name=e.event, showlegend=False,
            hovertext=f"{e.player} / {e.event} / {e.damage} dmg"))
    fig.update_layout(height=570, template="plotly_dark", paper_bgcolor="#0b131e",
        plot_bgcolor="#101d2c", xaxis_title="X", yaxis_title="Y",
        xaxis=dict(scaleanchor="y", scaleratio=1), legend_title="チーム")
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("プレイヤー別戦績")
    stats = df.groupby(["player","ship","team"], dropna=False).agg(
        events=("event","count"), damage=("damage","sum"),
        hits=("event", lambda x: x.isin(["hit","torpedo_hit"]).sum()),
        shots=("event", lambda x: x.isin(["shot","torpedo"]).sum())
    ).reset_index()
    st.dataframe(stats, use_container_width=True, hide_index=True)
    st.subheader("発生イベント")
    if len(events_now):
        show = events_now[["time","player","ship","event","target","damage","detail"]].sort_values("time", ascending=False)
        st.dataframe(show, use_container_width=True, hide_index=True, height=230)
    else:
        st.caption("この時点までに戦闘イベントはありません。")

st.subheader("全イベント一覧")
st.dataframe(df, use_container_width=True, hide_index=True)

st.subheader("エクスポート")
a,b = st.columns(2)
with a:
    st.download_button("解析用JSONを書き出す", json.dumps({"events": df.to_dict("records")}, ensure_ascii=False, indent=2),
                       "replay_events.json", "application/json")
with b:
    st.download_button("CSVを書き出す", df.to_csv(index=False).encode("utf-8-sig"),
                       "replay_events.csv", "text/csv")

st.info(
    "MP4出力と連続再生は次段階で実装します。安定した動画生成には、"
    "イベント時刻ごとのフレーム生成とFFmpegが必要です。"
    "現状のスライダーは任意時刻への移動に対応しています。"
)
