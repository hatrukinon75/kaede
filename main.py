import discord
from discord.ext import commands
import random
import os
from dotenv import load_dotenv

# 読み込み実行
load_dotenv()

ROLES_ORDER = ['大崎', '有明', '新橋', '青海', '静馬', '汐留', '竹芝', '市場前', '船野', '豊洲', '品川']
bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())

def get_member_name(interaction, member_id):
    # すべてMember ID(int)とみなす
    member = interaction.guild.get_member(member_id)
    return member.display_name if member else f"ID:{member_id}"

class GameSession:
    def __init__(self, assignment_map, participants):
        self.assignment_map = assignment_map
        self.lovers = {}
        self.osaki_list = assignment_map.get('大崎', [])
        self.participants = participants 

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
        return "役職なし"

async def send_dm_to_member(interaction, member_id, message, view=None):
    member = await interaction.client.fetch_user(member_id)
    if member:
        try:
            await member.send(message, view=view)
        except Exception as e:
            print(f"DM送信中にエラー発生: {e}")

async def send_dm_to_member(interaction, member_id, message, view=None):
    """メンバーIDから確実にDMを送るための共通関数"""
    # ★修正: guild経由ではなく、interaction.client (bot) 経由で取得する
    # member_id が int 型（Discord ID）の場合のみ get_user を実行
    member = None
    if isinstance(member_id, int):
        member = interaction.client.get_user(member_id)
        # キャッシュにない場合に備えて取得を試みる
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
        # メンバーが見つからない場合（ダミーなど）
        print(f"メンバーが見つかりません (またはダミーです): {member_id}")

# --- 1. 管理用View (先に定義) ---
class ManagementView(discord.ui.View):
    def __init__(self, participants, result_counts, rule_type): # rule_typeを追加
        super().__init__(timeout=None)
        self.participants, self.result_counts, self.rule_type = participants, result_counts, rule_type

    @discord.ui.button(label="再抽選します。このまま", style=discord.ButtonStyle.secondary)
    async def reroll(self, interaction, button):
        # rule_typeを渡す
        await execute_assignment(interaction, self.participants, self.result_counts, self.rule_type)

    @discord.ui.button(label="やり直しますか。初めから", style=discord.ButtonStyle.danger)
    async def reset(self, interaction, button):
        await interaction.response.send_message("決め直します", view=EntryView(), ephemeral=True)

# --- 2. 配役実行関数 ---
async def execute_assignment(interaction, participants, counts, rule_type): # 引数追加
    shuffled = participants[:]
    random.shuffle(shuffled)
    assignment_map = {role: [] for role in ROLES_ORDER}
    current_idx = 0
    for role in ROLES_ORDER:
        count = counts.get(role, 0)
        assigned = shuffled[current_idx : current_idx + count]
        assignment_map[role] = [m.id if hasattr(m, 'id') else m for m in assigned]
        current_idx += count
    
    # 全体結果表示
    result_text = "### 配役結果です。\n"
    for role, members in assignment_map.items():
        if not members: continue
        mentions = [interaction.guild.get_member(m).mention if interaction.guild.get_member(m) else get_member_name(interaction, m) for m in members]
        result_text += f"\n**{role}**: {', '.join(mentions)}"
            
    # 管理Viewにも rule_type を渡す
    await interaction.response.send_message(result_text, view=ManagementView(participants, counts, rule_type))

    # ★修正: 恋人ルールの時だけ静馬にDMを送る
    if rule_type == 'lover':
        session = GameSession(assignment_map, participants)
        for shizuma_id in assignment_map.get('静馬', []):
            if isinstance(shizuma_id, int):
                await send_dm_to_member(interaction, shizuma_id, "静馬さん。選択してください。", view=LoverSelectionView(session, shizuma_id, participants))

# --- 3. ボタン式配役設定View ---
class RoleCounterView(discord.ui.View):
    def __init__(self, participants, counts, page, rule_type):
        super().__init__(timeout=None)
        self.participants, self.counts, self.page, self.rule_type = participants, counts, page, rule_type
        self.clear_items()

        start, end = page * 4, (page + 1) * 4
        roles = ROLES_ORDER[start:end]
        
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
        # ページ送りのロジック
        if (self.page + 1) * 5 < len(ROLES_ORDER):
            new_view = RoleCounterView(self.participants, self.counts, self.page + 1, self.rule_type)
            await interaction.response.edit_message(view=new_view)
        else:
            # --- ここにバリデーション（人数チェック）を追加 ---
            total_assigned = sum(self.counts.values())
            
            # 一色ルール以外の時だけチェックする
            if self.rule_type != "monochrome" and total_assigned != len(self.participants):
                await interaction.response.send_message(
                    f"合っていません。人数\n設定合計: {total_assigned}名 / 参加者: {len(self.participants)}名\n合計が参加人数と一致するように調整してください。",
                    ephemeral=True
                )
                return
            # ---------------------------------------------

            # 人数が合っていれば配役実行へ進む
            await execute_assignment(interaction, self.participants, self.counts, self.rule_type)

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
            
        await interaction.response.send_message("調整してください。人数", view=RoleCounterView(self.participants, counts, 0, rule_type), ephemeral=True)

    @discord.ui.button(label="通常ルール", style=discord.ButtonStyle.primary)
    async def normal(self, interaction, button): await self.start_setup(interaction, "normal")

    @discord.ui.button(label="恋人ルール", style=discord.ButtonStyle.primary)
    async def lover(self, interaction, button): await self.start_setup(interaction, "lover")

    @discord.ui.button(label="一色ルール", style=discord.ButtonStyle.primary)
    async def monochrome(self, interaction, button): await self.start_setup(interaction, "monochrome")

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
        # ここで恋人を登録
        self.session.set_lover(self.osaki, self.candidate)
        
        # 1. 大崎さんへのフィードバック
        await interaction.response.send_message("承諾しました。相手に伝えます。")
        
        o_name = self.session.get_name(self.osaki)
        c_name = self.session.get_name(self.candidate)
        
        # 2. 候補者（二人目）へのDM：確認ボタンだけを送る
        await send_dm_to_member(
            interaction, 
            self.candidate, 
            f"{o_name} さんが指名を承諾しました。\nあなたと {o_name} さんが恋人関係になります。確認ボタンを押して処理を完了してください。",
            view=CandidateConfirmView(self.shizuma, o_name, self.candidate)
        )

    @discord.ui.button(label="拒否", style=discord.ButtonStyle.danger)
    async def reject(self, interaction, button):
        # 拒否の処理は現状通りでOK
        self.session.set_lover(self.osaki, self.shizuma)
        await interaction.response.send_message("拒否しました。静馬さんと恋人になります。")
        
        shizuma_user = interaction.client.get_user(self.shizuma)
        if shizuma_user:
            o_name = self.session.get_name(self.osaki)
            await shizuma_user.send(
                f"{o_name} さんが拒否しました。 {o_name} さんはあなたと恋人になりたいようです。",
                view=CandidateConfirmView(self.shizuma, o_name, self.osaki)
            )

class OsakiSelectorView(discord.ui.View):
    def __init__(self, session, picker_id, shizuma_id): # shizuma_id を追加
        super().__init__(timeout=None)
        self.session = session
        self.picker_id = picker_id
        self.shizuma_id = shizuma_id # 保持する
        
        options = []
        for osaki_id in session.osaki_list:
            name = self.session.get_name(osaki_id)
            label = f"大崎さん ({name})"
            options.append(discord.SelectOption(label=label, value=str(osaki_id)))
            
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
        
        picker_name = self.session.get_name(self.picker_id)
        
        # ★ここを変更：選ばれた大崎さんに直接「指名通知＋確認ボタン」を送る
        await send_dm_to_member(
            interaction, 
            osaki_id, 
            f"{picker_name} さんから恋人として指名されました。確認ボタンを押して処理を完了してください。",
            view=CandidateConfirmView(self.shizuma_id, picker_name, osaki_id)
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
            
            role_name = self.session.get_role_by_member(u.id)
            label = f"{u.display_name} ({role_name})"
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
            # 静馬と大崎本人を除外
            if u.id in [shizuma_id, osaki_id] or self.session.is_osaki(u.id):
                continue
            
            role_name = self.session.get_role_by_member(u.id)
            label = f"{u.display_name} ({role_name})"
            options.append(discord.SelectOption(label=label, value=str(u.id)))
            
        self.select = discord.ui.Select(placeholder="恋人候補を選択", options=options)
        self.select.callback = self.select_candidate
        self.add_item(self.select)

    async def select_candidate(self, interaction: discord.Interaction):
        candidate_id = int(self.select.values[0])
        candidate_name = self.session.get_name(candidate_id)
        
        msg = f"静馬から指名されました。相手は {candidate_name} さんです。承諾しますか？"
        await send_dm_to_member(interaction, self.osaki_id, msg, 
                                view=OsakiDecisionView(self.session, self.shizuma_id, self.osaki_id, candidate_id))
        await interaction.response.send_message("大崎さんに交渉を依頼しました。", ephemeral=True)

class CandidateConfirmView(discord.ui.View):
    def __init__(self, shizuma_id, osaki_name, candidate_id):
        super().__init__(timeout=None)
        self.shizuma_id = shizuma_id
        self.osaki_name = osaki_name # この場合、指名した人の名前が入ります
        self.candidate_id = candidate_id

    @discord.ui.button(label="確認", style=discord.ButtonStyle.success)
    async def confirm(self, interaction, button):
        self.session.set_lover(self.candidate_id, self.shizuma_id)

        # 静馬さんにDMを送信
        try:
            shizuma_user = await interaction.client.fetch_user(self.shizuma_id)
            if shizuma_user:
                await shizuma_user.send("恋人成立処理が完了しました。")
        except Exception as e:
            print(f"静馬への通知失敗: {e}")
        
        # 押した人（大崎さん）へのフィードバック
        await interaction.response.send_message("確認しました。恋人関係が確定しました。")

@bot.tree.command(name="startgame")
async def startgame(interaction): await interaction.response.send_message(view=EntryView())

raw_token = os.getenv('MY_BOT_SECRET_TOKEN')

bot.run(raw_token)