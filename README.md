# WoWS Legends Replay Creator (MVP)

## 起動方法
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

## 現在できること
- JSON / CSV のイベントデータ読み込み
- 時刻スライダーによる戦況の巻き戻し・早送り
- 全プレイヤーの最新位置表示
- 主砲・魚雷などのイベント表示
- プレイヤー別のダメージ・命中・発射数集計
- JSON / CSV 書き出し

## 入力データ仕様
JSONは `{"events": [...]}`、CSVは同じ列構成です。

必須列:
- `time`: 戦闘開始からの秒数
- `player`: プレイヤー名または識別子
- `ship`: 艦艇名
- `x`, `y`: マップ上の座標
- `event`: `position`, `shot`, `hit`, `torpedo`, `torpedo_hit`, `sink` など

任意列:
- `target`, `damage`, `team`, `hp`, `detail`

## 重要な技術的制約
本MVPはゲーム独自の `.wowsreplay` を生成したり復号したりしません。
ゲームが受け付けるネイティブリプレイを新規生成するには、公式の書き込み可能なリプレイ仕様、暗号化/署名方式、バージョン互換性が必要です。これらが公開・確認できない限り、独自データを `.wowsreplay` として出力することはできません。
まず解析済みイベントデータを共通形式にし、マップ再生・統計・動画化を実装する設計です。
