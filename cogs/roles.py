import json
import os
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "data", "roles_config.json")


def load_config() -> dict:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_user_permissions(member: discord.Member, config: dict) -> list[dict]:
    allowed = []
    member_role_ids = {r.id for r in member.roles}
    superadmin_id = config.get("superadmin_role_id")
    is_superadmin = bool(superadmin_id and superadmin_id in member_role_ids)

    for dept_key, dept in config["departments"].items():
        dept_roles = dept["roles"]
        emoji = dept.get("emoji", "⭐")

        if is_superadmin:
            for r in dept_roles:
                if r["id"] != 0:
                    allowed.append({"role_id": r["id"], "role_name": r["name"],
                                    "dept_key": dept_key, "dept_name": dept["name"], "dept_emoji": emoji})
            continue

        user_level = max(
            (r["level"] for r in dept_roles if r["id"] in member_role_ids),
            default=None
        )
        if user_level is None:
            continue

        grantable = dept["can_grant"].get(str(user_level), [])
        for r in dept_roles:
            if r["level"] in grantable and r["id"] != 0:
                allowed.append({"role_id": r["id"], "role_name": r["name"],
                                "dept_key": dept_key, "dept_name": dept["name"], "dept_emoji": emoji})

    return allowed


async def log_action(config: dict, client: discord.Client, action: str,
                     grantor: discord.Member, target: discord.Member,
                     role: discord.Role, dept_name: str):
    channel_id = config.get("log_channel_id", 0)
    if not channel_id:
        return
    channel = client.get_channel(channel_id)
    if not channel:
        return
    color = discord.Color.green() if action == "выдана" else discord.Color.red()
    embed = discord.Embed(title=f"🔐 Роль {action}", color=color, timestamp=datetime.now())
    embed.add_field(name="Кто",   value=f"{grantor.mention} (`{grantor}`)", inline=True)
    embed.add_field(name="Кому",  value=f"{target.mention} (`{target}`)",   inline=True)
    embed.add_field(name="Роль",  value=role.mention,  inline=True)
    embed.add_field(name="Отдел", value=dept_name,     inline=True)
    await channel.send(embed=embed)


class ConfirmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)
        self.confirmed: bool | None = None

    @discord.ui.button(label="Да, уверен", style=discord.ButtonStyle.danger, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Отмена", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        self.stop()
        await interaction.response.edit_message(
            embed=discord.Embed(description="Действие отменено.", color=discord.Color.light_grey()),
            view=None
        )


class RoleSelect(discord.ui.Select):
    def __init__(self, allowed_roles: list[dict], target: discord.Member, action: str):
        self.target = target
        self.action = action
        options = [
            discord.SelectOption(
                label=r["role_name"],
                value=str(r["role_id"]),
                description=r["dept_name"],
                emoji=r["dept_emoji"]
            )
            for r in allowed_roles
        ]
        placeholder = "Выдать роль..." if action == "give" else "Снять роль..."
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        config = load_config()
        role_id = int(self.values[0])
        grantor = interaction.user

        allowed = get_user_permissions(grantor, config)
        if role_id not in [r["role_id"] for r in allowed]:
            return await interaction.response.send_message(
                embed=discord.Embed(description="❌ У тебя нет прав на эту роль.", color=discord.Color.red()),
                ephemeral=True
            )

        role = interaction.guild.get_role(role_id)
        if not role:
            return await interaction.response.send_message(
                embed=discord.Embed(description="❌ Роль не найдена. Проверь конфиг.", color=discord.Color.red()),
                ephemeral=True
            )

        role_info = next(r for r in allowed if r["role_id"] == role_id)
        dept_key = role_info["dept_key"]
        dept_name = role_info["dept_name"]
        dept_role_id = config["departments"][dept_key].get("dept_role_id", 0)
        dept_role = interaction.guild.get_role(dept_role_id) if dept_role_id else None

        if self.action == "give":
            if role in self.target.roles:
                return await interaction.response.send_message(
                    embed=discord.Embed(description=f"У {self.target.mention} уже есть {role.mention}.", color=discord.Color.orange()),
                    ephemeral=True
                )
            confirm = ConfirmView()
            await interaction.response.send_message(
                embed=discord.Embed(description=f"Выдать {role.mention} участнику {self.target.mention}?", color=discord.Color.purple()),
                view=confirm, ephemeral=True
            )
            await confirm.wait()
            if not confirm.confirmed:
                return
            roles_to_add = [r for r in [role, dept_role] if r]
            await self.target.add_roles(*roles_to_add, reason=f"Выдано {grantor}")
            await log_action(config, interaction.client, "выдана", grantor, self.target, role, dept_name)
            await interaction.edit_original_response(
                embed=discord.Embed(description=f"✅ Роль {role.mention} выдана {self.target.mention}.", color=discord.Color.green()),
                view=None
            )
        else:
            if role not in self.target.roles:
                return await interaction.response.send_message(
                    embed=discord.Embed(description=f"У {self.target.mention} нет {role.mention}.", color=discord.Color.orange()),
                    ephemeral=True
                )
            confirm = ConfirmView()
            await interaction.response.send_message(
                embed=discord.Embed(description=f"Снять {role.mention} с {self.target.mention}?", color=discord.Color.purple()),
                view=confirm, ephemeral=True
            )
            await confirm.wait()
            if not confirm.confirmed:
                return
            roles_to_remove = [role]
            if dept_role:
                dept_role_ids = {r["id"] for r in config["departments"][dept_key]["roles"]}
                if not any(r for r in self.target.roles if r.id in dept_role_ids and r.id != role_id):
                    roles_to_remove.append(dept_role)
            await self.target.remove_roles(*roles_to_remove, reason=f"Снято {grantor}")
            await log_action(config, interaction.client, "снята", grantor, self.target, role, dept_name)
            await interaction.edit_original_response(
                embed=discord.Embed(description=f"✅ Роль {role.mention} снята с {self.target.mention}.", color=discord.Color.green()),
                view=None
            )


class RolePanelView(discord.ui.View):
    def __init__(self, allowed_roles: list[dict], target: discord.Member):
        super().__init__(timeout=120)
        self.add_item(RoleSelect(allowed_roles, target, "give"))
        self.add_item(RoleSelect(allowed_roles, target, "take"))


class Roles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="roles", description="Открыть панель управления ролями")
    @app_commands.describe(member="Участник, которому выдать/снять роль")
    async def roles_panel(self, interaction: discord.Interaction, member: discord.Member):
        if member == interaction.user:
            return await interaction.response.send_message(
                embed=discord.Embed(description="❌ Нельзя управлять своими ролями.", color=discord.Color.red()),
                ephemeral=True
            )

        config = load_config()
        allowed = get_user_permissions(interaction.user, config)

        if not allowed:
            return await interaction.response.send_message(
                embed=discord.Embed(description="❌ У тебя нет прав для управления ролями.", color=discord.Color.red()),
                ephemeral=True
            )

        embed = discord.Embed(title="🔐 Панель управления ролями", color=discord.Color.purple())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Участник", value=member.mention, inline=True)
        embed.add_field(name="Доступных ролей", value=str(len(allowed)), inline=True)
        embed.set_footer(text="Первый список — выдать, второй — снять")
        await interaction.response.send_message(embed=embed, view=RolePanelView(allowed, member))


async def setup(bot: commands.Bot):
    await bot.add_cog(Roles(bot))
