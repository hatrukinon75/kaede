import discord
import datetime
import asyncio
from discord.ext import commands
from discord import app_commands
import random
import os
from dotenv import load_dotenv
import random

active_sessions = {}
game_players = {}
poke_counts = {}
# 読み込み実行
load_dotenv()

ONW_ROLES = ['人狼', '村人', '占い師', '怪盗', 'てるてる']
ROLE_EMOJI_MAP = {
    '大崎': '<:pic_amus_oh:1516961522117509190>',
    '有明': '<:pic_amus_ar:1516961995549839380>',
    '新橋': '<:pic_amus_sn:1516962641782767709>',
    '青海': '<:pic_amus_ao:1516963152216985833>',
    '静馬': '<:pic_amus_sz:1516961912636838049>',
    '汐留': '<:pic_amus_shio:1519363293138128896>',
    '竹芝': '<:pic_amus_take:1518636176188117062>',
    '市場前': '<:pic_amus_shij:1519365469646098463>',
    '船野': '<:pic_amus_fune:1519362692970840155>',
    '豊洲': '<:pic_amus_toyo:1519365416693006449>',
    '品川': '<:pic_amus_sina:1519362005725614290>',
}
ROLES_ORDER = ['大崎', '有明', '新橋', '青海', '静馬', '汐留', '竹芝', '市場前', '船野', '豊洲', '品川']
ROLES_ORDER_MOB = ['メインモブ']
bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())

#def get_member_name(interaction, member_id):
#    # すべてMember ID(int)とみなす
#    member = interaction.guild.get_member(member_id)
#    return member.display_name if member else f"ID:{member_id}"

def get_member_name(interaction, member_or_id):
    # 1. IDが文字列で "dummy_" から始まる場合（ダミーと判定）
    if isinstance(member_or_id, str) and member_or_id.startswith("dummy_"):
        # "dummy_ダミー1" などの文字列から "dummy_" を取り除いて "ダミー1" を返す
        return member_or_id.replace("dummy_", "")

    # 2. メンバーオブジェクトが直接渡された場合（念のため）
    if hasattr(member_or_id, 'display_name'):
        return member_or_id.display_name

    # 3. ID(int) が渡された場合（通常のユーザー）
    if isinstance(member_or_id, int):
        # サーバー内から取得を試みる
        if interaction.guild:
            member = interaction.guild.get_member(member_or_id)
            if member:
                return member.display_name # mentionではなく名前にする場合はこれ
        
        # 取得できない場合はキャッシュから
        user = bot.get_user(member_or_id)
        if user:
            return user.name
            
        return f"ユーザー(ID:{member_or_id})"

    # 4. それ以外
    return str(member_or_id)

def safe_parse_id(value):
    """IDがダミーならそのまま（文字列）、ユーザーIDならintに変換する関数"""
    if isinstance(value, str) and value.startswith("dummy_"):
        return value
    return int(value)

## ★デバッグ用ダミー★ ##
class DummyMember:
    def __init__(self, name):
        self.id = f"dummy_{name}" # 一意のIDとして識別
        self.display_name = name
        self.mention = f"**{name} (ダミー)**"

## ★デバッグ用ダミー★ ##

class GameSession:
    def __init__(self, assignment_map, participants, main_channel, deck_roles=None, pc_map=None):
        self.pc_map = pc_map or {}
        self.assignment_map = assignment_map
        self.participants = participants
        self.deck_roles = deck_roles or []
        self.lovers = {}
        self.osaki_list = assignment_map.get('大崎', [])
        self.deck_seen = False
        self.votes = {}        # {voter_id: target_id} を保存
        self.main_channel = main_channel # 発表用のチャンネル

    def get_formatted_name(self, member_id):
        # メンバーオブジェクトを探す
        member = next((m for m in self.participants if m.id == member_id), None)
        name = member.display_name if member else "不明"
        
        # PCマップからPC名を取得（なければ「PCなし」と表示）
        pc_name = self.pc_map.get(member_id, "PCなし")
        
        # 望んでいた「ユーザー名（PC名）」の形にする
        return f"{name}（{pc_name}）"

    def get_deck_info(self):
        """中央のカード（占い師が見る2枚）の情報を返す"""
        if not self.deck_roles:
            return "（情報がありません）"
        
        # 配列の中身を文字列として結合して返す例
        return "、".join(self.deck_roles)

    def get_name(self, member_id):
        # 参加者リストからメンバーを検索
        for p in self.participants:
            if p.id == member_id:
                return p.display_name
        return f"ID:{member_id}"

    def is_osaki(self, member_id):
        return member_id in self.osaki_list

    def set_lover(self, member_id, lover_id):
        self.lovers[member_id] = lover_id
        self.lovers[lover_id] = member_id
    
    def has_lover(self, member_id):
        return member_id in self.lovers

    def get_role_by_member(self, member_id):
        for role, members in self.assignment_map.items():
            if member_id in members:
                return role
        return "不明"

    def add_vote(self, voter_id, target_id):
        self.votes[voter_id] = target_id

    def is_all_voted(self):
        return len(self.votes) == len(self.participants)

    def get_member_info(self, member_id):
        # ★デバッグ出力：何で検索しようとしているかを表示
        print(f"DEBUG: 検索ID='{member_id}'(型:{type(member_id)}), マップの中身={list(self.pc_map.keys())}")
        
        member = next((m for m in self.participants if m.id == member_id), None)
        name = member.display_name if member else "不明"
        
        pc_name = self.pc_map.get(member_id, "PCなし")
        
        return f"{name}（{pc_name}）"

    async def announce_result(self):
        raw_channel = self.main_channel
        if isinstance(raw_channel, list):
            # リストなら最初の要素を取り出す
            channel = raw_channel[0]
            print(f"DEBUG: main_channelがリストでした。修正して続行します。中身: {channel}")
        else:
            channel = raw_channel
            
        # 念のためのチェック（もしNoneなどになっていたら動かないので）
        if not channel:
            print("ERROR: channelが取得できませんでした")
            return
        
        # 1. 投票集計（既存のロジック）
        vote_counts = {}
        for target_id in self.votes.values():
            vote_counts[target_id] = vote_counts.get(target_id, 0) + 1
        
        if not vote_counts: return
        max_votes = max(vote_counts.values())
        targets = [uid for uid, count in vote_counts.items() if count == max_votes]
        
        # 2. 発表メッセージ作成
        result_msg = "### 【投票結果発表】\n"
        
        # 同票対応
        if len(targets) > 1:
            result_msg += f"最多得票者が複数名（{len(targets)}名）のため、処刑なしです。\n人狼の勝利です！"
        else:
            lynched_id = targets[0]
            name = self.get_name(lynched_id)
            lynched_role = self.get_role_by_member(lynched_id)
            
            result_msg += f"最多得票者は **{name}** さんです。\n"
            result_msg += f"処刑されたプレイヤーの役職は…… **{lynched_role}** でした。\n\n"
            
            # ★勝利条件判定
            if lynched_role == "人狼":
                result_msg += "人狼が処刑されました！ **村人の勝利です！**"
                await channel.send(result_msg)
                await self.announce_winner("村人") # ここで追加メソッドを呼ぶ
                
            elif lynched_role == "てるてる":
                result_msg += "てるてるが処刑されました！ **てるてるの勝利です！**"
                await channel.send(result_msg)
                await self.announce_winner("てるてる") # ここで追加メソッドを呼ぶ
                
            else:
                result_msg += "処刑されたのは村人側です。 **人狼の勝利です！**"
                await channel.send(result_msg)
                await self.announce_winner("人狼")
        
        await channel.send(result_msg)

        async def announce_winner(self, winner_role):
            """勝利チームとメンバーをメンションで発表する"""
            # 勝利チームのIDリストを取得
            winner_ids = self.assignment_map.get(winner_role, [])
            
            # メンションリストを作成
            mention_list = []
            for m_id in winner_ids:
                member = next((m for m in self.participants if m.id == m_id), None)
                if member:
                    mention_list.append(member.mention)
            
            # メッセージ送信
            mentions_str = " ".join(mention_list) if mention_list else "（メンバーが見つかりません）"
            msg = f"🏆 **ゲーム終了！** 🏆\n勝利チーム：**{winner_role}**\n勝者：{mentions_str}"
             
            await self.main_channel.send(msg)

async def send_dm_to_member(interaction, member_id, message, view=None):
    """メンバーIDから確実にDMを送るための共通関数"""

## ★デバッグ用ダミー★ ##

    if isinstance(member_id, DummyMember):
        print(f"ダミー {member_id.display_name} へのDMはスキップされました")
        return

## ★デバッグ用ダミー★ ##

    # メンバー取得
    member = None
    if isinstance(member_id, int):
        member = interaction.client.get_user(member_id)
        if not member:
            try:
                member = await interaction.client.fetch_user(member_id)
            except:
                pass
    
    if member:
        try:
            await member.send(message, view=view)
        except discord.Forbidden:
            print(f"DM送信失敗: {member.display_name} はDMをブロックしています。")
        except Exception as e:
            print(f"DM送信中にエラー発生: {e}")
    else:
        print(f"メンバーが見つかりません: {member_id}")

# --- 1. 管理用View (先に定義) ---
class ManagementView(discord.ui.View):
    def __init__(self, participants, result_counts, rule_type, roles_list): 
        super().__init__(timeout=None)
        self.participants, self.result_counts, self.rule_type = participants, result_counts, rule_type
        self.roles_list = roles_list # 保存する

    @discord.ui.button(label="再抽選します。このまま", style=discord.ButtonStyle.secondary)
    async def reroll(self, interaction, button):
        await execute_assignment(interaction, self.participants, self.result_counts, self.rule_type, self.roles_list)

    @discord.ui.button(label="やり直しますか。初めから", style=discord.ButtonStyle.danger)
    async def reset(self, interaction, button):
        await interaction.response.send_message("決め直します", view=EntryView(), ephemeral=True)

# --- 2. 配役実行関数 ---
async def execute_assignment(interaction, participants, counts, rule_type, roles_list=ROLES_ORDER):
    # 1. 参加者をシャッフルして役職を割り当て
    shuffled = participants[:]
    random.shuffle(shuffled)
    assignment_map = {role: [] for role in roles_list}
    current_idx = 0
    for role in roles_list:
        count = counts.get(role, 0)
        assigned = shuffled[current_idx : current_idx + count]
        assignment_map[role] = [m.id if hasattr(m, 'id') else m for m in assigned]
        current_idx += count

    # 2. PCマップを作成 (id: PC名 の対応表)
    # ここで各プレイヤーに「PC1」「PC2」...または任意の名前を割り当てます
    pc_map = {}
    for i, member in enumerate(participants):
        m_id = member.id if hasattr(member, 'id') else member
        # ここでPC名を決定します（例: "PC 1", "PC 2"...）
        # ※ もし特定の名前リストがあればここを差し替えてください
        pc_map[m_id] = f"PC {i + 1}"

    # 3. GameSessionの初期化
    # ※GameSessionクラスの __init__ でも pc_map を受け取るようにしてください
    session = GameSession(assignment_map, participants, interaction.channel, pc_map=pc_map)
    active_sessions[interaction.guild_id] = session

    # 4. 配役結果のテキスト生成
    result_text = "### 配役結果です。\n"
    for role, members in assignment_map.items():
        if not members: continue
        
        emoji = ROLE_EMOJI_MAP.get(role, "")
        display_emoji = f"{emoji} " if emoji else ""

        formatted_players = []
        for m_id in members:
            # メンションまたは名前を取得
            if interaction.guild:
                member = interaction.guild.get_member(m_id)
                name = member.mention if member else get_member_name(interaction, m_id)
            else:
                name = get_member_name(interaction, m_id)
            
            # PC名を取得
            pc_name = pc_map.get(m_id, "不明")
            
            # 表示: "プレイヤー名（PC名 / 役職名）"
            formatted_players.append(f"{name}（{pc_name} / {role}）")
        
        result_text += f"\n{display_emoji}**{role}**: {', '.join(formatted_players)}"
            
    await interaction.response.send_message(result_text, view=ManagementView(participants, counts, rule_type, roles_list))

    # 5. 恋人ルールの時だけDMを送る処理
    if rule_type == 'lover':
        for shizuma_id in assignment_map.get('静馬', []):
            if isinstance(shizuma_id, int):
                await send_dm_to_member(interaction, shizuma_id, "静馬さん。選択してください。", view=LoverSelectionView(session, shizuma_id, participants))

# --- 3. ボタン式配役設定View ---
class RoleCounterView(discord.ui.View):
    def __init__(self, participants, counts, page, rule_type, roles_list=ROLES_ORDER):
        super().__init__(timeout=None)
        self.participants, self.counts, self.page, self.rule_type = participants, counts, page, rule_type
        self.roles_list = roles_list # 保存
        self.clear_items()

        start, end = page * 4, (page + 1) * 4
        roles = self.roles_list[start:end]
        
        # 役職ごとのボタン
        for i, role in enumerate(roles):
            self.add_item(discord.ui.Button(label=role, style=discord.ButtonStyle.secondary, disabled=True, row=i))
            
            btn_minus = discord.ui.Button(label="－", style=discord.ButtonStyle.danger, custom_id=f"minus_{role}", row=i)
            btn_minus.callback = self.change_count
            self.add_item(btn_minus)
            
            btn_count = discord.ui.Button(label=str(self.counts[role]), style=discord.ButtonStyle.primary, custom_id=f"num_{role}", row=i)
            btn_count.callback = self.change_count
            self.add_item(btn_count)
            
            btn_plus = discord.ui.Button(label="＋", style=discord.ButtonStyle.primary, custom_id=f"plus_{role}", row=i)
            btn_plus.callback = self.change_count
            self.add_item(btn_plus)

        if self.page > 0:
            btn_back = discord.ui.Button(label="前へ", style=discord.ButtonStyle.secondary, row=4)
            btn_back.callback = self.prev_page
            self.add_item(btn_back)

        is_last = (page + 1) * 5 >= len(ROLES_ORDER)
        label = "配役実行" if is_last else "次へ"
        btn_next = discord.ui.Button(label=label, style=discord.ButtonStyle.success, row=4)
        btn_next.callback = self.next_page
        self.add_item(btn_next)

    async def change_count(self, interaction):
        custom_id = interaction.data['custom_id']
        action, role = custom_id.split('_')
        
        if action == 'minus':
            if self.counts[role] > 0: self.counts[role] -= 1
        elif action == 'plus':
            self.counts[role] += 1
            
        # ★修正: rule_type を渡す
        await interaction.response.edit_message(view=RoleCounterView(self.participants, self.counts, self.page, self.rule_type))

    async def prev_page(self, interaction):
        # ★修正: rule_type を渡す
        new_view = RoleCounterView(self.participants, self.counts, self.page - 1, self.rule_type)
        await interaction.response.edit_message(view=new_view)

    async def next_page(self, interaction):
        if (self.page + 1) * 5 < len(self.roles_list):
            new_view = RoleCounterView(self.participants, self.counts, self.page + 1, self.rule_type, self.roles_list)
            await interaction.response.edit_message(view=new_view)
        else:
            total_assigned = sum(self.counts.values())

            if self.rule_type != "monochrome" and self.rule_type != "mob" and total_assigned != len(self.participants):
                await interaction.response.send_message(
                    f"合っていません。人数\n設定合計: {total_assigned}名 / 参加者: {len(self.participants)}名\n合計が参加人数と一致するように調整してください。",
                    ephemeral=True
                )
                return

            # 配役実行時に roles_list を渡す
            await execute_assignment(
                interaction, 
                self.participants, 
                self.counts, 
                self.rule_type, 
                roles_list=self.roles_list
            )

# --- 4. ルール選択View (2ボタン式) ---
class RuleSelectionView(discord.ui.View):
    def __init__(self, participants):
        super().__init__()
        self.participants = participants

    async def start_setup(self, interaction, rule_type):
        total = len(self.participants)
        counts = {role: 0 for role in ROLES_ORDER}
        
        if rule_type == "normal":
            for i in range(total): counts[ROLES_ORDER[i % len(ROLES_ORDER)]] += 1
        elif rule_type == "lover":
            counts['大崎'] = max(1, (total - 1) // 2)
            counts['静馬'] = 1
            rem = max(0, total - sum(counts.values()))
            targets = [r for r in ROLES_ORDER if r not in ['大崎', '静馬']]
            for i in range(rem): counts[targets[i % len(targets)]] += 1
        elif rule_type == "monochrome":
            # 一色モード：大崎以外は0人からスタート
            counts['大崎'] = 1
        elif rule_type == "mob":
            # モブちん船：メインモブ1のみ指定
            counts['メインモブ'] = 1
        await interaction.response.send_message("調整してください。人数", view=RoleCounterView(self.participants, counts, 0, rule_type), ephemeral=True)

    @discord.ui.button(label="通常ルール", style=discord.ButtonStyle.primary)
    async def normal(self, interaction, button): await self.start_setup(interaction, "normal")

    @discord.ui.button(label="恋人ルール", style=discord.ButtonStyle.primary)
    async def lover(self, interaction, button): await self.start_setup(interaction, "lover")

    @discord.ui.button(label="一色ルール", style=discord.ButtonStyle.primary)
    async def monochrome(self, interaction, button): await self.start_setup(interaction, "monochrome")

    @discord.ui.button(label="モブちん船", style=discord.ButtonStyle.secondary)
    async def mob_mode(self, interaction, button):
        total = len(self.participants)
        # モブちん船用のカウント設定
        counts = {'メインモブ': 1}
        # 実行時に役職リストを渡して設定画面へ
        await interaction.response.send_message(
            "人数を調整してください。", 
            view=RoleCounterView(self.participants, counts, 0, "mob", roles_list=ROLES_ORDER_MOB), 
            ephemeral=True
        )

# --- 5. エントリーView ---
class EntryView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.participants = []

    @discord.ui.button(label="参加", style=discord.ButtonStyle.green)
    async def join(self, interaction, button):
        if interaction.user not in self.participants:
            self.participants.append(interaction.user)
            # 全体に向けてメッセージを送信
            await interaction.channel.send(f"{interaction.user.mention} さんが挙手しました！ (現在 {len(self.participants)} 名)")
            # 自身の応答は ephemeral=True でOK
            await interaction.response.send_message("受付ました。参加", ephemeral=True)
        else:
            await interaction.response.send_message("既に参加しています。", ephemeral=True)

## ★デバッグ用ダミー★ ##

    @discord.ui.button(label="ダミー追加", style=discord.ButtonStyle.secondary)
    async def add_dummy(self, interaction, button):
        # 既存のダミーの名前から番号を抽出してリスト化
        dummy_indices = []
        for p in self.participants:
            # 名前が「ダミー」で始まるか確認
            if hasattr(p, 'display_name') and p.display_name.startswith("ダミー"):
                try:
                    # 「ダミー」という文字列を削って数字を取得
                    num_str = p.display_name.replace("ダミー", "")
                    if num_str.isdigit():
                        dummy_indices.append(int(num_str))
                except:
                    pass
        
        # 次の番号を決定（リストが空なら1、それ以外は最大値+1）
        next_num = max(dummy_indices) + 1 if dummy_indices else 1
        name = f"ダミー{next_num}"
        
        # ダミー生成と追加
        dummy = DummyMember(name)
        self.participants.append(dummy)
        
        await interaction.response.send_message(f"{name} を追加しました。", ephemeral=True)
        # 全体に向けて通知
        await interaction.channel.send(f"{dummy.mention} さんが追加されました！ (現在 {len(self.participants)} 名)")

## ★デバッグ用ダミー★ ##

    @discord.ui.button(label="ルール選択へ", style=discord.ButtonStyle.primary)
    async def next(self, interaction, button):
        await interaction.response.send_message(view=RuleSelectionView(self.participants), ephemeral=True)

# 恋人セッティングターン(大崎) #
class OsakiDecisionView(discord.ui.View):
    def __init__(self, session, shizuma_id, osaki_id, candidate_id):
        super().__init__(timeout=None)
        self.session = session
        self.shizuma = shizuma_id
        self.osaki = osaki_id
        self.candidate = candidate_id

    @discord.ui.button(label="承諾", style=discord.ButtonStyle.success)
    async def accept(self, interaction, button):
        self.session.set_lover(self.osaki, self.candidate)
        await interaction.response.send_message("承諾しました。相手に伝えます。")
        
        # 配役(サーバーネーム) 形式で取得
        o_formatted = self.session.get_formatted_name(self.osaki)
        c_formatted = self.session.get_formatted_name(self.candidate)
        
        await send_dm_to_member(
            interaction, 
            self.candidate, 
            f"{o_formatted} さんが指名を承諾しました。\nあなたと {o_formatted} さんが恋人関係になります。\n確認ボタンを押し、処理を完了してください。",
            view=CandidateConfirmView(self.session, self.shizuma, self.osaki, self.candidate)
        )

    @discord.ui.button(label="拒否", style=discord.ButtonStyle.danger)
    async def reject(self, interaction, button):
        self.session.set_lover(self.osaki, self.shizuma)
        await interaction.response.send_message("拒否しました。静馬さんと恋人になります。")
        
        shizuma_user = interaction.client.get_user(self.shizuma)
        if shizuma_user:
            o_formatted = self.session.get_formatted_name(self.osaki)
            await shizuma_user.send(
                f"{o_formatted} さんが拒否しました。\n{o_formatted} さんはあなたと恋人になりたいようです。",
                view=CandidateConfirmView(self.session, self.shizuma, self.osaki, self.osaki) # 修正が必要なら調整
            )

class OsakiSelectorView(discord.ui.View):
    def __init__(self, session, picker_id, shizuma_id):
        super().__init__(timeout=None)
        self.session = session
        self.picker_id = picker_id
        self.shizuma_id = shizuma_id
        
        options = []
        for osaki_id in session.osaki_list:
            name = self.session.get_name(osaki_id)
            label = f"大崎({name})"
            options.append(discord.SelectOption(
                label=name, 
                value=str(member.id)
            ))
            
        self.select = discord.ui.Select(placeholder="選んでください。好きな大崎さん。", options=options)
        self.select.callback = self.select_osaki 
        self.add_item(self.select)

    async def select_osaki(self, interaction: discord.Interaction):
        osaki_id = int(self.select.values[0])
        if self.session.has_lover(osaki_id):
            await interaction.response.send_message("不成立でした。その大崎さんには既に恋人がいます。", ephemeral=True)
            return

        self.session.set_lover(self.picker_id, osaki_id)
        await interaction.response.send_message("大崎さんに指名通知を送りました。", ephemeral=True)
        
        # 配役(サーバーネーム) 形式で取得
        picker_formatted = self.session.get_formatted_name(self.picker_id)
        
        # DM送信
        message = f"恋人指名を受けています。\n{picker_formatted} さんから指名されました。\n確認ボタンを押し、処理を完了してください。"
        
        await send_dm_to_member(
            interaction, 
            osaki_id, 
            message,
            # ここで確認Viewを呼び出す（後述の修正でIDを渡すように変更します）
            view=CandidateConfirmView(self.session, self.shizuma_id, self.picker_id, osaki_id)
        )

class LoverSelectionView(discord.ui.View):
    def __init__(self, session, shizuma_id, participants):
        super().__init__(timeout=None)
        self.session = session
        self.shizuma_id = shizuma_id
        self.participants = participants

        options = []
        for u in participants:
            if u.id == self.shizuma_id: continue
            
            label = self.session.get_formatted_name(u.id)
            options.append(discord.SelectOption(label=label, value=str(u.id)))
        
        self.select = discord.ui.Select(placeholder="恋人候補を選択", options=options)
        self.select.callback = self.select_lover
        self.add_item(self.select)

    async def select_lover(self, interaction: discord.Interaction):
        target_id = int(self.select.values[0])
        
        if self.session.is_osaki(target_id):
            await interaction.response.send_message("大崎さんですね。恋人にする相手を選んでください。", ephemeral=True)
            await interaction.followup.send("相手選択:", 
                                            view=OsakiCandidateSelectionView(self.session, self.shizuma_id, target_id, self.participants), 
                                            ephemeral=True)
        else:
            await send_dm_to_member(interaction, target_id, "不純同性交友の指名です。選んでください。大崎さんから", 
                                    view=OsakiSelectorView(self.session, target_id, self.shizuma_id))
            await interaction.response.send_message("相手に指名を送りました。", ephemeral=True)

class OsakiCandidateSelectionView(discord.ui.View):
    def __init__(self, session, shizuma_id, osaki_id, participants):
        super().__init__()
        self.session = session
        self.shizuma_id = shizuma_id
        self.osaki_id = osaki_id
        
        options = []
        for u in participants:
            if u.id in [shizuma_id, osaki_id] or self.session.is_osaki(u.id):
                continue
            
            label = self.session.get_formatted_name(u.id)
            options.append(discord.SelectOption(label=label, value=str(u.id)))
            
        self.select = discord.ui.Select(placeholder="恋人候補を選択", options=options)
        self.select.callback = self.select_candidate
        self.add_item(self.select)

    async def select_candidate(self, interaction: discord.Interaction):
        candidate_id = int(self.select.values[0])
        
        # ここでフォーマット済みネームを取得
        candidate_formatted = self.session.get_formatted_name(candidate_id)
        
        msg = f"静馬から指名されました。\n相手は {candidate_formatted} さんです。\n承諾しますか？"
        
        await send_dm_to_member(interaction, self.osaki_id, msg, 
                                view=OsakiDecisionView(self.session, self.shizuma_id, self.osaki_id, candidate_id))
        await interaction.response.send_message("大崎さんに交渉を依頼しました。", ephemeral=True)

class CandidateConfirmView(discord.ui.View):
    def __init__(self, session, shizuma_id, target_id, confirm_id):
        super().__init__(timeout=None)
        self.session = session
        self.shizuma_id = shizuma_id
        self.target_id = target_id # 指名した人（または大崎）
        self.confirm_id = confirm_id # ボタンを押す人

    @discord.ui.button(label="確認", style=discord.ButtonStyle.success)
    async def confirm(self, interaction, button):
        self.session.set_lover(self.confirm_id, self.shizuma_id)

        # 静馬さんにDMを送信
        try:
            shizuma_user = await interaction.client.fetch_user(self.shizuma_id)
            if shizuma_user:
                await shizuma_user.send("恋人成立処理が完了しました。")
        except:
            pass
        
        await interaction.response.send_message("確認しました。恋人関係が確定しました。")

class SeerSelectView(discord.ui.View):
    def __init__(self, session, initiator_id):
        # timeout=None にすると、時間が経ってもボタンが消えなくなります（ゲーム向け）
        super().__init__(timeout=None) 
        self.session = session
        self.initiator_id = initiator_id # これも保存しておくと便利
        
        options = []
        options.append(discord.SelectOption(label="中央のカードを占う", value="center"))

        for member in session.participants:
            if member.id != initiator_id:
                options.append(discord.SelectOption(label=member.display_name, value=str(member.id)))
        
        # --- 修正点：self.select に代入する ---
        self.select = discord.ui.Select(placeholder="占う相手を選んでください", options=options)
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        self.select.disabled = True
        val = self.select.values[0]
        
        # 画面を更新するために disable した選択メニューを送信
        await interaction.response.edit_message(view=self)

        if val == "center":
            roles = self.session.deck_roles
            if len(roles) >= 2:
                # 占い結果を分かりやすく
                result = f"中央のカードは **{roles[0]}** と **{roles[1]}** です。"
            else:
                result = "中央のカードが正しく設定されていません。"
        else:
            # プレイヤーを選択した場合
            target_id = int(val)
            target_info = self.session.get_member_info(target_id) # 名前(駅名)を取得
            role = self.session.get_role_by_member(target_id)    # 役職名を取得
            
            # 役職名を表示（黒白判定ではなく具体的な役職を表示）
            result = f"{target_info} の役職は…… **{role}** でした。"

        # 結果をDMに送る（または現在のチャンネルに送信）
        await interaction.followup.send(result, ephemeral=True)

class ThiefSelectView(discord.ui.View):
    def __init__(self, session, thief_id):
        super().__init__(timeout=None)
        self.session = session
        self.thief_id = thief_id

        options = []
        # 自分以外の参加者を表示
        for p in session.participants:
            if p.id != thief_id:
                options.append(discord.SelectOption(label=p.display_name, value=str(p.id)))
        
        self.select = discord.ui.Select(placeholder="誰の役職を盗みますか？", options=options)
        self.select.callback = self.select_target
        self.add_item(self.select)

    async def select_target(self, interaction):
        # 1. 選択メニューを無効化
        self.select.disabled = True
        
        target_id = safe_parse_id(self.select.values[0])
        target_info = self.session.get_member_info(target_id)
        
        # 1. 現在の役職を取得
        thief_role = self.session.get_role_by_member(self.thief_id)
        target_role = self.session.get_role_by_member(target_id)
        
        # 2. assignment_map を入れ替える
        # リストからIDを移動させる
        self.session.assignment_map[thief_role].remove(self.thief_id)
        self.session.assignment_map[target_role].remove(target_id)
        
        self.session.assignment_map[target_role].append(self.thief_id)
        self.session.assignment_map[thief_role].append(target_id)
        
        my_new_role = target_role
        
        # 3. 怪盗に結果を伝える
        result = f"{target_info} と交換しました。\nあなたの新しい役職は **{my_new_role}** です。"
        await interaction.response.edit_message(content=result, view=self)

class OnwRoleCounterView(discord.ui.View):
    def __init__(self, participants, counts, page=0):
        super().__init__(timeout=None)
        self.participants = participants
        self.counts = counts
        self.page = page
        self.roles_list = ONW_ROLES
        self.render_buttons()

    def render_buttons(self):
        self.clear_items()
        
        # 1ページあたり4役職ずつ表示
        start, end = self.page * 4, (self.page + 1) * 4
        current_roles = self.roles_list[start:end]

        for i, role in enumerate(current_roles):
            row = i # 1役職を1行使う
            
            # 役職名（4アイテム置くと残り1枠なので、ここを工夫してシンプルにする）
            # もしくは、役職名ボタンの代わりにラベルを表示する方法もありますが、
            # 今回はButtonのラベルを工夫して「役職名」自体をボタンにして配置します
            
            # 1. 役職名（無効化）
            self.add_item(discord.ui.Button(label=role, style=discord.ButtonStyle.secondary, disabled=True, row=row))
            # 2. マイナス
            btn_m = discord.ui.Button(label="－", style=discord.ButtonStyle.danger, custom_id=f"minus_{role}", row=row)
            btn_m.callback = self.change_count
            self.add_item(btn_m)
            # 3. 数値
            self.add_item(discord.ui.Button(label=str(self.counts.get(role, 0)), style=discord.ButtonStyle.primary, disabled=True, row=row))
            # 4. プラス
            btn_p = discord.ui.Button(label="＋", style=discord.ButtonStyle.primary, custom_id=f"plus_{role}", row=row)
            btn_p.callback = self.change_count
            self.add_item(btn_p)

        # ページ移動ボタン or 実行ボタンを最終行(Row 4)に配置
        row_nav = 4
        if self.page > 0:
            btn_back = discord.ui.Button(label="前へ", style=discord.ButtonStyle.secondary, row=row_nav)
            btn_back.callback = self.prev_page
            self.add_item(btn_back)

        if (self.page + 1) * 4 < len(self.roles_list):
            btn_next = discord.ui.Button(label="次へ", style=discord.ButtonStyle.secondary, row=row_nav)
            btn_next.callback = self.next_page
            self.add_item(btn_next)
        else:
            btn_exec = discord.ui.Button(label="配役を実行", style=discord.ButtonStyle.success, row=row_nav)
            btn_exec.callback = self.execute
            self.add_item(btn_exec)

    async def change_count(self, interaction):
        action, role = interaction.data['custom_id'].split('_')
        if action == 'minus' and self.counts.get(role, 0) > 0:
            self.counts[role] -= 1
        elif action == 'plus':
            self.counts[role] += 1
        
        # 画面を更新
        await interaction.response.edit_message(view=OnwRoleCounterView(self.participants, self.counts, self.page))

    async def prev_page(self, interaction):
        await interaction.response.edit_message(view=OnwRoleCounterView(self.participants, self.counts, self.page - 1))

    async def next_page(self, interaction):
        await interaction.response.edit_message(view=OnwRoleCounterView(self.participants, self.counts, self.page + 1))

    async def execute(self, interaction):
        # (executeの中身はそのまま変更なし)
        total_assigned = sum(self.counts.values())
        required = len(self.participants) + 3
        
        if total_assigned != required:
            await interaction.response.send_message(f"合計枚数が間違っています。\n現在: {total_assigned}枚 / 必要: {required}枚", ephemeral=True)
            return
            
        current_owen_map={}
        await execute_onw_assignment(
            interaction, 
            self.participants, 
            self.counts, 
            current_owen_map=current_owen_map
        )

async def execute_onw_assignment(interaction, participants, counts, current_owen_map):
    # 1. 処理中であることを伝える
    await interaction.response.defer(ephemeral=False)

    # ★ここを修正：current_owen_map が空なら、ここで強制的に作成する
    pc_map = current_owen_map
    if not pc_map:
        # もしマップが渡されていなければ、ここで自動生成する
        pc_map = {m.id: f"PC {i + 1}" for i, m in enumerate(participants)}

    # 2. 全役職のリスト(pool)を作成
    pool = []
    for role, count in counts.items():
        pool.extend([role] * count)
    
    random.shuffle(pool)
    
    # 3. リストを「プレイヤー用」と「中央用」に分ける
    player_roles = pool[:len(participants)]
    deck_roles = pool[len(participants):]
    
    # 4. assignment_map を作成
    assignment_map = {role: [] for role in counts.keys()}
    for i, member in enumerate(participants):
        role = player_roles[i]
        assignment_map[role].append(member.id)
    
    # 5. PCマップ（old: owen_map -> new: pc_map）
    # ※GameSession側でも pc_map という名前で受け取るようにしてください
    pc_map = {}
    for i, member in enumerate(participants):
        # 確実に member.id を取得
        m_id = getattr(member, 'id', member)
        pc_map[m_id] = f"PC {i + 1}"
        print(f"DEBUG: マップに登録 -> {m_id} : PC {i + 1}")
    
    # 6. セッション開始
    session = GameSession(
        assignment_map=assignment_map,
        participants=participants,
        main_channel=interaction.channel,
        deck_roles=deck_roles,
        pc_map=pc_map  # ここで修正済みの pc_map を渡す
    )
    active_sessions[interaction.guild.id] = session
    
    # DM送信ループ
    for member in participants:
        # ★直接 pc_map を見るのではなく、セッションのメソッドを通す
        role = session.get_role_by_member(member.id)
        
        # get_member_info は既にPC名を表示するよう修正済みのはずです
        # ここで「名前（PC名）」の文字列を取得します
        member_info_str = session.get_member_info(member.id) 
        
        msg = f"【ワンナイト人狼】\nあなたの役職（カード）は **{role}** です。\n{member_info_str} です。"
        
        # 人狼の処理
        if role == "人狼":
            other_werewolves = [
                session.get_member_info(m.id) # ここで上の修正したメソッドが呼ばれる
                for m in participants 
                if m.id in session.assignment_map.get("人狼", []) and m.id != member.id
            ]
            
            if other_werewolves:
                msg += f"\n\nもう一人の人狼は **{', '.join(other_werewolves)}** さんです。"
            else:
                msg += "\n\n人狼はあなた一人です。"

        # ビューの設定
        final_view = None
        if role == "占い師":
            final_view = SeerSelectView(session, member.id)
        elif role == "怪盗":
            final_view = ThiefSelectView(session, member.id)
        
        await send_dm_to_member(interaction, member.id, msg, view=final_view)

    # 完了メッセージ
    await interaction.followup.send(
        "### 配役が完了しました。\n夜のアクションが済みましたら、以下のボタンから投票を開始してください。", 
        view=GameStartView(session)
    )

class PlayerActionView(discord.ui.View):
    def __init__(self, session, member_id, role):
        super().__init__(timeout=None)
        self.session = session
        self.member_id = member_id
        self.role = role

        if role == "占い師":
            btn = discord.ui.Button(label="占う", style=discord.ButtonStyle.primary, custom_id="seer")
            btn.callback = self.seer_callback
            self.add_item(btn)
        elif role == "怪盗":
            btn = discord.ui.Button(label="交換する", style=discord.ButtonStyle.danger, custom_id="thief")
            btn.callback = self.thief_callback
            self.add_item(btn)

    # 共通の無効化処理
    async def disable_all_buttons(self, interaction: discord.Interaction):
        for item in self.children:
            item.disabled = True
        # ボタンを無効化した状態でメッセージを更新（これで連打が効かなくなる）
        await interaction.response.edit_message(view=self)

    async def seer_callback(self, interaction: discord.Interaction):
        # 1. まずボタンを無効化
        await self.disable_all_buttons(interaction)
        
        # 2. 次の画面（占い先の選択）を followup で送信
        await interaction.followup.send(view=SeerSelectView(self.session, self.member_id), ephemeral=True)

    async def thief_callback(self, interaction: discord.Interaction):
        # 1. まずボタンを無効化
        await self.disable_all_buttons(interaction)
        
        # 2. 次の画面（交換先の選択）を followup で送信
        await interaction.followup.send(view=ThiefSelectView(self.session, self.member_id), ephemeral=True)

class VoteView(discord.ui.View):
    def __init__(self, session, member):
        super().__init__(timeout=None)
        self.session = session
        self.member = member
        
        # 選択肢の作成（自分以外をリストアップ）
        options = [
            discord.SelectOption(label=m.display_name, value=str(m.id))
            for m in self.session.participants if m.id != member.id
        ]
        
        self.select = discord.ui.Select(placeholder="投票先を選んでください", options=options)
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        # 1. 投票を保存
        target_id = int(self.select.values[0])
        self.session.add_vote(self.member.id, target_id)
        
        # 2. UIを無効化（連打防止）
        self.select.disabled = True
        await interaction.response.edit_message(content="投票を受け付けました。発表をお待ちください。", view=self)
        
        # 3. 全員が投票済みか確認
        if self.session.is_all_voted():
            await self.session.announce_result()

class GameStartView(discord.ui.View):
    def __init__(self, session):
        super().__init__(timeout=None)
        self.session = session

    @discord.ui.button(label="投票開始", style=discord.ButtonStyle.danger, emoji="⚖️")
    async def start_vote(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 連打防止：ボタンを無効化
        button.disabled = True
        await interaction.response.edit_message(content="投票フェーズを開始しました。", view=self)
        
        # 全員に投票DMを送る
        for member in self.session.participants:
            # 投票用のView（先ほど作ったVoteView）を呼び出す
            await send_dm_to_member(interaction, member.id, "議論は終わりましたか？誰を処刑しますか？", view=VoteView(self.session, member))

# DM対応用つつくコマンド
class PokeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="つつく", style=discord.ButtonStyle.primary)
    async def poke(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        
        # 回数をカウントアップ
        count = poke_counts.get(user_id, 0) + 1
        poke_counts[user_id] = count
        
        # 3回、6回、9回で反応を変える
        if count == 3:
            await interaction.response.send_message("なぜ。こんなところを。", ephemeral=True)
        elif count == 6:
            await interaction.response.send_message("や。やめてください。もう……。", ephemeral=True)
        elif count == 9:
            await interaction.response.send_message("……あっ。", ephemeral=True)
        elif count == 12:
            await interaction.response.send_message("……っ。軽蔑します。", ephemeral=True)
            poke_counts[user_id] = 0 # リセット
        else:
            await interaction.response.send_message("ん……。", ephemeral=True)

async def run_timer(user, hours):
    """指定された時間（時間）待機してからDMを送る処理"""
    seconds = hours * 3600  # 1時間 = 3600秒
    
    # 待機（テストしたい場合は一時的に seconds を 10 などに変更してください）
    await asyncio.sleep(seconds)
    
    # 時間経過後のDM送信
    try:
        if hours == 0.05:
            await user.send(f"🔔 時間です。3分。")
        else:
            await user.send(f"🔔 時間です。{hours}時間も。作業お疲れ様でした")

    except discord.Forbidden:
        print(f"{user.name} へのDM送信に失敗しました（DM拒否されています）")

class TimeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="3分", value="0.05", description="では3分後に。メッセージを"),
            discord.SelectOption(label="1時間", value="1", description="では1時間後に。メッセージを"),
            discord.SelectOption(label="2時間", value="2", description="では2時間後に。メッセージを"),
            discord.SelectOption(label="3時間", value="3", description="では3時間後に。メッセージを"),
        ]
        super().__init__(placeholder="作業時間を選択してください", options=options)

    async def callback(self, interaction: discord.Interaction):
        hours = float(self.values[0])
        
        # 非同期タスクとしてタイマーを開始（これでコマンド応答は即座に返ります）
        asyncio.create_task(run_timer(interaction.user, hours))
        
        if hours == 0.05:
            await interaction.response.send_message(
                f"🕒 では。3分後に。", 
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"🕒 では。{hours}時間後に。", 
                ephemeral=True
            )

class TimeSelectView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(TimeSelect())

############################
# ------呼び出し専用------ #
############################

@bot.tree.command(name="startgame", description="ゲームを開始します")
async def startgame(interaction: discord.Interaction):
    # 応答済みでなければ defer する
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=False)
    
    # 既に処理済み（またはdefer成功後）なら followup で送る
    await interaction.followup.send("ゲームを開始します！参加ボタンを押してください。", view=EntryView())

@bot.tree.command(name="endgame", description="現在のゲームを終了し、情報を破棄します")
async def endgame(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    
    if guild_id not in active_sessions:
        await interaction.response.send_message("現在開催中のゲームはありません。", ephemeral=True)
        return
    
    # 情報を破棄（辞書から削除）
    del active_sessions[guild_id]
    
    await interaction.response.send_message("ゲームを終了します。お疲れさまでした。")

@bot.tree.command(name="onenight", description="ワンナイト人狼モードへ移行します")
async def onenight(interaction: discord.Interaction):
    # 応答済みでなければ defer する
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True)

    try:
        guild_id = interaction.guild_id
        session = active_sessions.get(guild_id)
        
        if not session:
            await interaction.followup.send(
                "まだゲームが開始されていません。\n`/startgame` で募集を開始してください。", 
                ephemeral=True
            )
            return
        
        participants = session.participants
        initial_counts = {role: 0 for role in ONW_ROLES}
        
        await interaction.followup.send(
            f"人数を調整してください（参加者 {len(participants)} 名 + 余り3枚 = 合計 {len(participants)+3} 枚）",
            view=OnwRoleCounterView(participants, initial_counts),
            ephemeral=True
        )

    except Exception as e:
        print(f"ERROR in /onenight: {e}")
        # すでに処理済みの可能性があるため followup を使用
        if not interaction.response.is_done():
             await interaction.response.send_message("エラーが発生しました。", ephemeral=True)
        else:
             await interaction.followup.send("エラーが発生しました。", ephemeral=True)

@bot.tree.command(name="work", description="タイマーメニューを表示")
async def start_timer(interaction: discord.Interaction):
    await interaction.response.send_message("どのくらいでしょうか。作業：", view=TimeSelectView())

@bot.event
async def on_message(message):
    # 1. Bot自身の発言なら終了
    if bot.user is None or message.author.id == bot.user.id:
        return

    # ユーザーがメッセージを送ったら、その人のカウントを強制リセット
    if isinstance(message.channel, discord.DMChannel):
        poke_counts[message.author.id] = 0

    # DEBUGログ
    print(f"DEBUG [{datetime.datetime.now().strftime('%H:%M:%S.%f')}]: メッセージ受信 - {message.author}: {message.content}")

    # 2. DMかどうかを判定
    if isinstance(message.channel, discord.DMChannel):

        if "おはよ" in message.content:
            await message.channel.send("おはようございます。もう食べましたか。朝食")

        elif "おやすみ" in message.content:
            await message.channel.send("おやすみなさい。もう寝ます。私も")

        elif "こんにちは" in message.content:
            await message.channel.send("こんにちは。昼ですか。もう")

        elif "こんばんは" in message.content:
            await message.channel.send("こんばんは。お疲れ様でした。今日も")

        elif "終わ" in message.content:
            await message.channel.send("お疲れさまでした。最後までやり遂げられるということは。偉いです。とても")

        elif "おわ" in message.content:
            await message.channel.send("お疲れさまでした。最後までやり遂げられるということは。偉いです。とても")

        elif "作業" in message.content:
            await message.channel.send("頑張ってください。……応援しています")

        elif "大崎" in message.content:
            await message.channel.send("……緋色さんですか。いえ……")

        elif "卓一" in message.content:
            await message.channel.send("……。")

        elif "好き" in message.content:
            await message.channel.send("……。受け取っておきます。好意は。")

        elif "結婚して" in message.content:
            await message.channel.send("その。それは……。困ります。")

        elif "いちご" in message.content:
            await message.channel.send("私に。ですか。…好きなんです。いちご。")

        elif "合唱" in message.content:
            await message.channel.send("好きですか。歌。")

        elif "楓" in message.content:
            await message.channel.send("呼びましたか。", view=PokeView())

        elif "かえで" in message.content:
            await message.channel.send("呼びましたか。", view=PokeView())

    await bot.process_commands(message)

bot.run(os.getenv('MY_BOT_SECRET_TOKEN'))