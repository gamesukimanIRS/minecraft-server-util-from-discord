import discord
import os
import json
import ruamel.yaml
import shutil
import copy
import re
import asyncio
import requests
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from dotenv import load_dotenv
from rcon.source import Client

# .envを読み込み
load_dotenv()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
RCON_HOST = os.getenv("RCON_HOST")
RCON_PORT = int(os.getenv("RCON_PORT"))
RCON_PASSWORD = os.getenv("RCON_PASSWORD")

YAHOO_APPID = os.getenv("YAHOO_APPID")
CHANNEL_ID = int(os.getenv('CHANNEL_ID'))
LOG_FILE_PATH = os.getenv('LOG_FILE_PATH', 'logs/latest.log')

GUILD_IDS = None

# --- 設定ファイルの準備と読み込み ---
DEFAULT_CONFIG_FILE = 'default_settings.yml'
USER_CONFIG_FILE = 'settings.yml'

if not os.path.exists(USER_CONFIG_FILE):
    try:
        shutil.copy(DEFAULT_CONFIG_FILE, USER_CONFIG_FILE)
        print(f"'{USER_CONFIG_FILE}' not found. Copied from '{DEFAULT_CONFIG_FILE}'.")
    except FileNotFoundError:
        print(f"FATAL: Default config file '{DEFAULT_CONFIG_FILE}' not found.")
        exit()

def deep_merge(source, destination):
    for key, value in source.items():
        if isinstance(value, dict):
            node = destination.setdefault(key, {})
            deep_merge(value, node)
        else:
            destination.setdefault(key, value)
    return destination

try:
    yaml = ruamel.yaml.YAML()
    with open(DEFAULT_CONFIG_FILE, 'r', encoding='utf-8') as f:
        default_config = yaml.load(f)
    with open(USER_CONFIG_FILE, 'r', encoding='utf-8') as f:
        user_config = yaml.load(f)
    
    MESSAGES = deep_merge(default_config, user_config)
    
    print(f"Message formats loaded and merged from '{DEFAULT_CONFIG_FILE}' and '{USER_CONFIG_FILE}'.")
except Exception as e:
    print(f"Error loading config files: {e}")
    exit()

# --- 正規表現パターン(サーバーログ分析で使用) ---
try:
    CHAT_PATTERN = re.compile(MESSAGES['settings']['regex_patterns']['chat'])
    LAG_WARNING_PATTERN = re.compile(MESSAGES['settings']['regex_patterns']['lag'])
    JOIN_PATTERN = re.compile(MESSAGES['settings']['regex_patterns']['join'])
    LEAVE_PATTERN = re.compile(MESSAGES['settings']['regex_patterns']['leave'])
except KeyError as e:
    print(f"FATAL: Regex patterns not found or invalid in formats.json. Key not found: {e}")
    exit()

# グローバル変数としてObserverを定義
log_observer = Observer()

# whitelistログファイル名
LOG_FILE = "whitelist_log.json"
ADMIN_USER_ID = 0

# --- whitelistログ読み書き関数 ---

def load_log():
    """whitelistログを読み込む"""
    if not os.path.exists(LOG_FILE):
        return {}
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def save_log(log_data):
    """whitelistログに保存する"""
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=4)

# --- Discordに送信するヘルパー ---
async def send_message_to_discord(self, message):
    try:
        channel = self.bot.get_channel(CHANNEL_ID)
        if channel: await channel.send(message)
    except Exception as e: print(MESSAGES['console']['log_processing_error'].format(error=e))

# --- Serverに送信するヘルパー ---
def send_command_to_server(command, isPost=False, executor=None):
    try:
        print(f"{MESSAGES['console']['rcon_command_sent'].format(command=command)}{MESSAGES['console']['rcon_executor'].format(executor=executor) if executor else ''}")
        with Client(RCON_HOST, RCON_PORT, passwd=RCON_PASSWORD) as client:
            response = client.run(command)
        if isPost:
            print(MESSAGES['console']['server_response'].format(command=command, response=response))
            return response
        else:
            return True
    except Exception as e:
        print(MESSAGES['console']['rcon_connection_error'].format(error=e))
        return False

# --- ローマ字チャットのかな漢字変換 ---
def convert_japanese_yahoo(text: str) -> str:
    """Yahoo JLP APIを使い、ローマ字をかな漢字交じり文に変換する。"""
    if not YAHOO_APPID:
        print(MESSAGES['console']['yahoo_appid_missing'])
        return text

    api_url = "https://jlp.yahooapis.jp/JIMService/V2/conversion"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": f"Yahoo AppID: {YAHOO_APPID}",
    }
    payload = {
        "id": "1234-1",
        "jsonrpc": "2.0",
        "method": "jlp.jimservice.conversion",
        "params": {
            "q": text,
            "format": "roman",
            "mode": "kanakanji",
            "results": 1 # 最も可能性の高い候補のみ取得
        }
    }
    
    try:
        response = requests.post(api_url, data=json.dumps(payload), headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()

        if "result" in data and "segment" in data["result"]:
            # 各セグメントの最初の候補を結合して文を再構築
            return "".join([seg["candidate"][0] for seg in data["result"]["segment"]])

    except requests.RequestException as e:
        print(MESSAGES['console']['yahoo_request_failed'].format(error=e))
    except (IndexError, KeyError) as e:
        print(MESSAGES['console']['yahoo_parse_failed'].format(error=e))
        
    # 失敗した場合は元のテキストをそのまま返す
    return text

class LogFileHandler(FileSystemEventHandler):
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.last_position = 0
        # 起動時にファイルの末尾にシーク
        if os.path.exists(LOG_FILE_PATH):
            try: self.last_position = os.path.getsize(LOG_FILE_PATH)
            except OSError: pass # ファイルがすぐに消された場合などを考慮

    # --- Discordに送信するヘルパー ---
    async def send_message_to_discord(self, message):
        try:
            channel = self.bot.get_channel(CHANNEL_ID)
            if channel: await channel.send(message)
        except Exception as e: print(MESSAGES['console']['log_processing_error'].format(error=e))

    async def process_chat_message(self, player_name, chat_message):
        """チャットメッセージを処理し、必要なら変換してDiscordに送信する"""
        is_romaji_only = not re.search(r'[ぁ-んァ-ン一-龯]', chat_message)

        if is_romaji_only:
            # Yahoo APIの関数を呼び出す
            final_text = await asyncio.to_thread(convert_japanese_yahoo, chat_message)
            
            # 変換前と変換後が同じでなければ、変換結果を併記
            if final_text != chat_message:
                replacevars = {
                    'player_name': player_name,
                    'converted_text': final_text,
                    'original_message': chat_message,
                }
                message_to_send = MESSAGES['discord']['chat_romaji_converted'].format(**replacevars)
                if MESSAGES['server']['to_server_chat_with_kanakanji']['enable']:
                    chatformat = MESSAGES['server']['to_server_chat_with_kanakanji']['format'].format(**replacevars)
                    if not send_command_to_server(f'say {chatformat}'):
                        print(MESSAGES['console']['server_send_failed'])

            else:
                message_to_send = (MESSAGES['discord']['chat_normal']
                .format(
                    player_name=player_name,
                    message=chat_message
                ))
        else:
            # 日本語が含まれる場合はそのまま送信
            message_to_send = (MESSAGES['discord']['chat_normal']
            .format(
                player_name=player_name,
                message=chat_message
            ))

        await self.send_message_to_discord(message_to_send)

    def on_modified(self, event):
        if not os.path.normpath(event.src_path) == os.path.normpath(LOG_FILE_PATH): return
        try:
            with open(LOG_FILE_PATH, 'r', encoding='utf-8', errors='ignore') as f:
                f.seek(self.last_position)
                new_lines = f.readlines()
                self.last_position = f.tell()

            for line in new_lines:

                chat_match = CHAT_PATTERN.search(line)
                lag_match = LAG_WARNING_PATTERN.search(line)
                join_match = JOIN_PATTERN.search(line)
                leave_match = LEAVE_PATTERN.search(line)

                message_to_send = None

                if chat_match:
                    player_name = chat_match.group(1)
                    chat_message = chat_match.group(2)
                    asyncio.run_coroutine_threadsafe(
                        self.process_chat_message(player_name, chat_message),
                        self.bot.loop
                    )
                    continue

                elif lag_match:
                    ms = lag_match.group(1)
                    ticks = lag_match.group(2)
                    message_to_send = MESSAGES['discord']['server_lag'].format(ms=ms, ticks=ticks)
                
                elif join_match:
                    message_to_send = MESSAGES['discord']['player_joined'].format(player_name=join_match.group(1))

                elif leave_match:
                    message_to_send = MESSAGES['discord']['player_left'].format(player_name=leave_match.group(1))

                # 送信するメッセージがあればDiscordに送る
                if message_to_send:
                    asyncio.run_coroutine_threadsafe(
                        self.send_message_to_discord(message_to_send),
                        self.bot.loop
                    )

        except Exception as e: print(MESSAGES['console']['log_processing_error'].format(error=e))


async def get_adder_name(guild: discord.Guild, adder_id: int):
    """IDから追加者の名前を取得する。キャッシュになければAPIに問い合わせる"""
    if adder_id == ADMIN_USER_ID: return MESSAGES['discord']['adders']['adder_admin']
    # まずキャッシュからメンバーを探す
    member = guild.get_member(adder_id)
    if not member:
        # キャッシュにいなければAPIに問い合わせる
        try: member = await guild.fetch_member(adder_id)
        # サーバーから既に脱退している場合
        except discord.NotFound: return MESSAGES['discord']['adders']['adder_unknown']
    # memberがNoneでない（見つかった）場合、その表示名を返す
    return member.display_name


# --- ホワイトリスト同期関数 ---
async def sync_whitelist_log(log_data):
    print(MESSAGES['console']['sync_started'])

    response = send_command_to_server("whitelist list", True)
    if response == False:
        print(MESSAGES['console']['sync_error'])
        return log_data
        
    # 結果からプレイヤー名を抜き出し
    match = re.search(MESSAGES['settings']['regex_patterns']['whitelist_list'], response)
    server_players = {name.strip() for name in match.group(1).split(',')} if match else set()
    
    # ホワイトリストログに記録あるか確認し、なければサーバー側での追加と見なす
    for player in server_players:
        if player.lower() not in log_data:
            log_data[player.lower()] = ADMIN_USER_ID
            print(MESSAGES['console']['sync_unlogged_player'].format(player=player))
    
    # ホワリスの中から、ログに記録があるがリストにないプレイヤー名を探し削除
    log_players = list(log_data.keys())
    for log_player_key in log_players:
        if not any(sp.lower() == log_player_key for sp in server_players):
            del log_data[log_player_key]
            print(MESSAGES['console']['sync_stale_player'].format(player=log_player_key))

    # ホワイトリストログを保存
    save_log(log_data)
    return log_data


# --- Botの準備 ---
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = discord.Bot(intents=intents)



@bot.event
async def on_ready():
    global log_observer
    print(MESSAGES['console']['bot_login'].format(user=bot.user))
    print("----------------------------------------")

    # ログ監視(watchdog)のセットアップと開始
    event_handler = LogFileHandler(bot)
    # ログファイルのあるディレクトリを監視対象にする
    log_directory = os.path.dirname(os.path.abspath(LOG_FILE_PATH))
    if not os.path.exists(log_directory):
        print(MESSAGES['console']['log_dir_not_found'].format(directory=log_directory))
        return
    log_observer.schedule(event_handler, log_directory, recursive=False)
    try:
        log_observer.start()
        print(MESSAGES['console']['observer_started'].format(directory=log_directory))
    except Exception as e:
        print(MESSAGES['console']['observer_start_failed'].format(error=e))

# --- on_message イベント ---
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot: return
    if message.channel.id != CHANNEL_ID: return
    if message.content.startswith("/"): return
    if not message.content: return

    nickname, content = message.author.display_name, message.clean_content
    safe_content = re.sub(r'(@)([aers])(?=\S)', r'\1.\2', content)
    messageformat = MESSAGES['server']['to_server_chat_format'].format(nickname=nickname, content=safe_content)

    if not send_command_to_server(f"say {messageformat}"):
        print(MESSAGES['console']['server_send_failed'])

try:
    ws_group_config = MESSAGES['commands']['ws']['group']
    ws = bot.create_group(name=ws_group_config['name'], description=ws_group_config['description'])

    # --- ホワイトリスト追加コマンド ---
    add_config = MESSAGES['commands']['ws']['subcommands']['add']
    @ws.command(name=add_config['name'], description=add_config['description'])
    async def add_player(ctx: discord.ApplicationContext, player_name: discord.Option(str, description=MESSAGES['commands']['options']['player_name'])):
        await ctx.defer()
        log_data = await sync_whitelist_log(load_log())
        command = f"whitelist add {player_name}"

        response = send_command_to_server(command, True, ctx.author.name)
        if not response:
            await ctx.respond(MESSAGES['discord']['error_generic'])
            return
        add_match = re.search(MESSAGES['settings']['regex_patterns']['add_success'], response, re.IGNORECASE)

        if add_match:
            correct_name = add_match.group(1)
            log_data[correct_name.lower()] = ctx.author.id
            save_log(log_data)
            await ctx.respond(MESSAGES['discord']['add_success'].format(player_name=correct_name))

        elif MESSAGES['settings']['non_regex_patterns']['already_whitelisted'] in response:
            adder_name = await get_adder_name(ctx.guild, log_data.get(player_name.lower(), ADMIN_USER_ID))
            await ctx.respond(MESSAGES['discord']['add_already_exists'].format(player_name=player_name, adder_name=adder_name))
        
        elif MESSAGES['settings']['non_regex_patterns']['player_not_exist'] in response:
            await ctx.respond(MESSAGES['discord']['no_such_player'].format(player_name=player_name))
            
        else:
            await ctx.respond(MESSAGES['discord']['error_generic'])
            print(MESSAGES['console']['unexpected_rcon_response'].format(response=response))


    # --- ホワイトリスト削除コマンド ---
    rem_config = MESSAGES['commands']['ws']['subcommands']['rem']
    @ws.command(name=rem_config['name'], description=rem_config['description'])
    async def remove_player(ctx: discord.ApplicationContext, player_name: discord.Option(str, description=MESSAGES['commands']['options']['player_name'])):
        await ctx.defer()
        log_data = await sync_whitelist_log(load_log())
        player_key = player_name.lower()
        adder_id = log_data.get(player_key)

        # Noneならplayer is not whitelistedなのかThat player does not existなのか分岐させたいので一度通す
        if adder_id is not None:
            if adder_id != ctx.author.id:
                # 表示名、"管理者"、"(不明なユーザー)"に変換
                adder_name = await get_adder_name(ctx.guild, adder_id)
                await ctx.respond(MESSAGES['discord']['remove_permission_denied'].format(player_name=player_name, adder_name=adder_name))
                return

        command = f"whitelist remove {player_name}"
        response = send_command_to_server(command, True, executor=ctx.author.name)
        if not response:
            await ctx.respond(MESSAGES['discord']['error_generic'])
            return

        remove_match = re.search(MESSAGES['settings']['regex_patterns']['remove_success'], response, re.IGNORECASE)
        
        if remove_match:
            correct_name = remove_match.group(1)
            if correct_name.lower() in log_data: del log_data[correct_name.lower()]
            save_log(log_data)
            await ctx.respond(MESSAGES['discord']['remove_success'].format(player_name=correct_name))

        elif MESSAGES['settings']['non_regex_patterns']['not_whitelisted'] in response:
            if player_key in log_data: del log_data[player_key]
            save_log(log_data)
            await ctx.respond(MESSAGES['discord']['remove_not_on_list'].format(player_name=player_name))

        elif MESSAGES['settings']['non_regex_patterns']['player_not_exist'] in response:
            await ctx.respond(MESSAGES['discord']['no_such_player'].format(player_name=player_name))

        else:
            await ctx.respond(MESSAGES['discord']['error_generic'])
            print(MESSAGES['console']['unexpected_rcon_response'].format(response=response))


    # --- ホワイトリスト表示コマンド ---
    list_config = MESSAGES['commands']['ws']['subcommands']['list']
    @ws.command(name=list_config['name'], description=list_config['description'])
    async def list_players(ctx: discord.ApplicationContext):
        await ctx.defer()
        log_data = await sync_whitelist_log(load_log())

        print(MESSAGES['console']['list_fetch_started'])
        response = send_command_to_server("whitelist list", True)
        if not response:
            await ctx.respond(MESSAGES['discord']['error_white_list_fetch_failed'])
            return
        
        embed = discord.Embed(color=0x784dbe, timestamp=discord.utils.utcnow())
        match = re.search(MESSAGES['settings']['regex_patterns']['whitelist_list'], response)

        if match:
            players = sorted([name.strip() for name in match.group(1).split(',')], key=str.lower)

            embed.description = MESSAGES['discord']['list_title'].format(count=len(players))

            for player in players:
                adder_id = log_data.get(player.lower(), ADMIN_USER_ID)
                adder_name = await get_adder_name(ctx.guild, adder_id)
                if adder_name in [MESSAGES['discord']['adders']['adder_admin'], MESSAGES['discord']['adders']['adder_unknown']]:
                    adder_name = MESSAGES['discord']['adders']['list_adder_na']
                embed.add_field(name=player, value=adder_name, inline=True)
        else:
            embed.description = MESSAGES['discord']['list_no_players']

        footer_text = MESSAGES['discord']['embed_footers']['whitelist']
        if bot.user.avatar: embed.set_footer(text=footer_text, icon_url=bot.user.avatar.url)
        else: embed.set_footer(text=footer_text)
        await ctx.respond(MESSAGES['discord']['whitelist_list_header'], embed=embed)


    # --- オンラインプレイヤー表示コマンド (/ls) ---
    online_config = MESSAGES['commands']['ls']
    @bot.slash_command(name=online_config['name'], description=online_config['description'])
    async def show_online_players(ctx: discord.ApplicationContext):
        """サーバーにオンラインのプレイヤーと、その追加者の一覧をEmbedで表示する"""
        await ctx.defer()
        # 追加者情報を参照するために、まずログを読み込む
        log_data = load_log()

        print("Fetching online player list...")
        response = send_command_to_server("list", True)
        if not response:
            await ctx.respond(MESSAGES['discord']['error_online_list_fetch_failed'])
            return

        embed = discord.Embed(color=0x784dbe, timestamp=discord.utils.utcnow())
        match = re.search(MESSAGES['settings']['regex_patterns']['online_list'], response)
        
        if match and match.group(1): # プレイヤーがいる場合
            players = sorted([name.strip() for name in match.group(1).split(',')], key=str.lower)

            embed.description = MESSAGES['discord']['online_title'].format(count=len(players))

            for player in players:
                adder_id = log_data.get(player.lower(), ADMIN_USER_ID)
                adder_name = await get_adder_name(ctx.guild, adder_id)
                if adder_name in [MESSAGES['discord']['adders']['adder_admin'], MESSAGES['discord']['adders']['adder_unknown']]:
                    adder_name = MESSAGES['discord']['adders']['list_adder_na']
                embed.add_field(name=player, value=adder_name, inline=True)

        else: # 誰もいない場合
            embed.description = MESSAGES['discord']['online_no_players']

        footer_text = MESSAGES['discord']['embed_footers']['online_players']
        if bot.user.avatar: embed.set_footer(text=footer_text, icon_url=bot.user.avatar.url)
        else: embed.set_footer(text=footer_text)
        await ctx.respond(MESSAGES['discord']['online_list_header'], embed=embed)

except KeyError as e:
    # config_load_errorはMESSAGESがロードされる前に発生する可能性があるためハードコード
    print(f"FATAL: A command definition is missing in config file. Key not found: {e}")
    exit()


if __name__ == "__main__":
    required_env = ["DISCORD_BOT_TOKEN", "RCON_HOST", "RCON_PORT", "RCON_PASSWORD", "YAHOO_APPID", "CHANNEL_ID", "LOG_FILE_PATH"]
    if not all(os.getenv(key) for key in required_env):
        print(MESSAGES['console']['env_missing'])
    else:
        try:
            bot.run(DISCORD_BOT_TOKEN)
        finally:
            # Botがどのような理由で停止しても、監視スレッドを止める
            if log_observer.is_alive():
                print("Stopping log file observer...")
                log_observer.stop()
                log_observer.join() # スレッドが完全に終了するのを待つ
                print("Log file observer stopped.")