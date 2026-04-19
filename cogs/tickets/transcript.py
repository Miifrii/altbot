import io
import discord

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>Транскрипция тикета {channel}</title>
<style>
  body {{ background: #36393f; color: #dcddde; font-family: Whitney, sans-serif; padding: 20px; }}
  .message {{ display: flex; gap: 12px; margin-bottom: 16px; }}
  .avatar {{ width: 40px; height: 40px; border-radius: 50%; }}
  .content {{ flex: 1; }}
  .author {{ font-weight: bold; color: #fff; }}
  .timestamp {{ font-size: 11px; color: #72767d; margin-left: 8px; }}
  .text {{ margin-top: 4px; white-space: pre-wrap; word-break: break-word; }}
  .attachment {{ color: #00b0f4; font-size: 13px; }}
  h1 {{ color: #fff; border-bottom: 1px solid #4f545c; padding-bottom: 10px; }}
</style>
</head>
<body>
<h1>📋 Транскрипция: #{channel}</h1>
{messages}
</body>
</html>"""

MSG_TEMPLATE = """<div class="message">
  <img class="avatar" src="{avatar}" onerror="this.src='https://cdn.discordapp.com/embed/avatars/0.png'">
  <div class="content">
    <span class="author">{author}</span>
    <span class="timestamp">{timestamp}</span>
    <div class="text">{text}</div>
    {attachments}
  </div>
</div>"""


async def generate_transcript(channel: discord.TextChannel) -> discord.File:
    messages_html = []
    async for msg in channel.history(limit=500, oldest_first=True):
        if msg.author.bot and msg.content == "" and not msg.embeds and not msg.attachments:
            continue
        attachments = "".join(
            f'<div class="attachment">📎 <a href="{a.url}" style="color:#00b0f4">{a.filename}</a></div>'
            for a in msg.attachments
        )
        messages_html.append(MSG_TEMPLATE.format(
            avatar=msg.author.display_avatar.url,
            author=str(msg.author),
            timestamp=msg.created_at.strftime("%d.%m.%Y %H:%M"),
            text=discord.utils.escape_mentions(msg.content or ""),
            attachments=attachments,
        ))

    html = HTML_TEMPLATE.format(channel=channel.name, messages="\n".join(messages_html))
    return discord.File(io.BytesIO(html.encode("utf-8")), filename=f"transcript-{channel.name}.html", spoiler=True)
