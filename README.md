# minecraft-server-util-from-discord
Discord bot for minecraft server utility without any plugin/mods  
本プログラムはgamesukimanIRSが記述したコードとGoogle Gemini 2.5 Proが記述したコードのブレンド品です。生成AIによるコードが含まれます。  

## 概要
MODやプラグインなどに一切依存せず、バニラサーバーや純粋なForge/NeoForgeサーバーでも利用可能な、Discord Botによるサーバーユーティリティです。  
現在、下記の機能があります。
- Discordスラッシュコマンドにより、各自で行うことができるホワイトリスト追加
  - ホワイトリスト追加者の記録(自身で追加することを想定し、MinecraftネームとDiscord名の紐づけを想定)
  - 他者が追加したメンバーや、botのログにない(コンソール追加など)追加メンバーの削除拒否
  - ホワイトリスト一覧
- 現在オンラインのプレイヤー一覧
- DiscordチャンネルとMinecraft内の相互チャット
  - Yahoo!のAPIを利用し、Minecraft内のローマ字チャットを自動変換
- overload警告を読み取り、接続チャンネルに遅延警告を送信
- `settings.yml`による、Botが発する全メッセージの任意設定

## 使用方法 (日本語)
### 0-1. ダウンロード
リポジトリを丸ごと落としてください。
### 0-2. RCONの有効化
連携対象のMinecraftサーバーの`server.properties`から、Rconを有効化してください。このとき、Rconポートの外部解放は行わないことを推奨します。  
本プログラムはMinecraftサーバーと同一のコンピュータ内で動作させる想定です。  
### 0-3. トークンとAPIキーの取得
Discord BotのAPIキーは[Discord デベロッパーポータル](https://discord.com/developers/applications)から取得し、後述の.env内に記述してください。  
Yahoo!かな漢字変換のAPIキーは[Yahoo! デベロッパーポータル](https://e.developer.yahoo.co.jp/dashboard/)から取得し、後述の.env内に記述してください。
### 1. .envの編集
`ToRename.env`を`.env`にリネームし、適切に編集してください。  
### 2. 依存関係のインストール
`pip install -r requirements.txt`で各ライブラリをインストールしてください。  
環境によってはPythonのvenvの利用が推奨されます。  
### 3. 実行
`python3 main.py`  
`whitelist_log.json`及び`settings.yml`が生成されます。
### 4. 設定の編集
`settings.yml`を開き、適切に編集してください。  
### 5. (要確認)ログファイルの権限設定
systemd実行などによってbotをminecraftサーバーと別ユーザーで起動する場合、server/logs/latest.logファイルへのr権限があるか確認してください。  

## Usage (English)
### 0-1. Download
Download the entire repository.  
### 0-2. Enable RCON
In your Minecraft server's `server.properties` file, enable RCON. It's recommended not to expose the RCON port to the public internet.  
This program is designed to run on the same machine as the Minecraft server.  
### 0-3. Obtain Tokens and API Keys
Get your Discord Bot API key from the **Discord Developer Portal** and add it to your `.env` file as described later. You can find the portal here: [https://discord.com/developers/applications](https://www.google.com/search?q=https://discord.com/developers/applications).
Similarly, obtain the Yahoo\! Kanji-Kana Conversion API key from the **Yahoo\! Developer Portal** and add it to your `.env` file. The portal is available at: [https://e.developer.yahoo.co.jp/dashboard/](https://e.developer.yahoo.co.jp/dashboard/).
### 1. Edit the .env file
Rename `ToRename.env` to `.env` and edit it as needed.  
### 2. Install dependencies
Install the required libraries with `pip install -r requirements.txt`.  
Using a Python venv is recommended, depending on your environment.  
### 3. Run
Run `python3 main.py`.  
This will generate `whitelist_log.json` and `settings.yml`.  
### 4. Edit settings  
Open `settings.yml` and edit it as needed.   
### 5. (Verify) Log file permissions
If you're running the bot as a different user than the Minecraft server (e.g., via systemd), ensure the bot has read (`r`) permission for the `server/logs/latest.log` file.  

## 設定ファイルについて
本プログラムには`.env`と`settings.yml`の2つの設定ファイルがあります。  
`.env`は環境変数ファイルであり、Discord及びYahoo!のAPIキーや、RCONサーバーのIP, Port, Password、接続するDiscordチャンネルのID、監視するログファイルのパスを指定します。  
`settings.yml`は全般設定ファイルであり、Botのコマンドエイリアスや、それに付随する説明、Botにより投稿されるメッセージ、転送されるチャットのフォーマット、監視するログのための正規表現などを編集できます。  
重要: `default_settings.yml`は`settings.yml`に異常がある場合に正常な設定値を持ってくるファイルですので、編集しないでください。  

This program uses two configuration files: `.env` and `settings.yml`.
The `.env` is the environment variable file. Here you will specify your Discord and Yahoo! API keys, the RCON server's IP, port, and password, the ID of the Discord channel you want to connect to, and the path to the log file that will be monitored.  
The `settings.yml` is the general settings file. In this file, you can customize the bot's command aliases, their descriptions, the messages the bot posts, the format for forwarded chat messages, and the regular expressions used for monitoring the log file.  
Important: Do not edit `default_settings.yml`. This file is used to restore proper settings if `settings.yml` becomes corrupted.  

## 利用技術
Discord Bot([Py-cord](https://pycord.dev/))  
Rcon(Minecraftサーバーへ)  
[Yahoo!かな漢字変換v2](https://developer.yahoo.co.jp/webapi/jlp/jim/v2/conversion.html)  

## 了承事項
Discord Bot自身の権限に注意してください。  
Minecraftと接続するチャンネルの閲覧権限・投稿権限に注意してください。スパムが投稿されると、そのままMinecraft内に転送される恐れがあります。  
短い間に大量の投稿(分間数百)が行われると、Yahoo!APIやDiscordAPIのレートリミットに抵触する可能性があります。  
本プログラムの利用にあたって起こることに関して、開発者はいかなる責任を負いません。  

## License
GPL v3.0
