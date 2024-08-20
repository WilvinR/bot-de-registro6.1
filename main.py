import os
import discord
from discord.ext import commands, tasks
import sqlite3
import aiohttp
import asyncio


# Configuración de intents y bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Nombre del archivo de base de datos
DB_FILE = "configuraciones.db"


# Modificación de la tabla en SQLite
def crear_tabla():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS guilds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_discord_id INTEGER,
        guild_id INTEGER,
        guild_name TEXT,
        tag TEXT,
        role_id INTEGER
    )
    """)
    conn.commit()
    conn.close()


crear_tabla()


# Función para guardar configuraciones de gremios múltiples
def guardar_configuracion(guild_discord_id, guild_name=None, tag=None, role_id=None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        """
    INSERT INTO guilds (guild_discord_id, guild_name, tag, role_id)
    VALUES (?, ?, ?, ?)
    """,
        (guild_discord_id, guild_name, tag, role_id),
    )

    conn.commit()
    conn.close()


# Función para cargar configuraciones de gremios múltiples
def cargar_configuraciones(guild_discord_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT guild_name, tag, role_id FROM guilds WHERE guild_discord_id = ?",
        (guild_discord_id,),
    )
    data = cursor.fetchall()

    conn.close()

    return [{"guild_name": row[0], "tag": row[1], "role_id": row[2]} for row in data]


# Función para eliminar un gremio específico
def eliminar_gremio(guild_discord_id, guild_name):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM guilds WHERE guild_discord_id = ? AND guild_name = ?",
        (guild_discord_id, guild_name),
    )
    conn.commit()
    conn.close()


# Adaptación de mostrar_menu para manejar múltiples gremios
async def mostrar_menu(ctx):
    guild_discord_id = ctx.guild.id
    configs = cargar_configuraciones(guild_discord_id)

    config_message = await ctx.send(
        "Selecciona lo que deseas configurar:\n"
        "1️⃣ Añadir nuevo gremio\n"
        "2️⃣ Eliminar gremio\n"
        "✅ Terminar"
    )

    emojis = ["1️⃣", "2️⃣", "✅"]
    for emoji in emojis:
        await config_message.add_reaction(emoji)

    def check(reaction, user):
        return (
            user == ctx.author
            and str(reaction.emoji) in emojis
            and reaction.message.id == config_message.id
        )

    reaction, user = await bot.wait_for("reaction_add", check=check)

    if str(reaction.emoji) == "1️⃣":
        await ctx.send("Introduce el nombre del nuevo gremio:")
        guild_name = await bot.wait_for(
            "message", check=lambda m: m.author == ctx.author
        )
        await ctx.send("Introduce el tag del nuevo gremio:")
        tag = await bot.wait_for("message", check=lambda m: m.author == ctx.author)
        await ctx.send("Menciona el rol del nuevo gremio:")
        role_msg = await bot.wait_for("message", check=lambda m: m.author == ctx.author)
        role = discord.utils.get(ctx.guild.roles, mention=role_msg.content.strip())
        if role:
            guardar_configuracion(
                guild_discord_id,
                guild_name=guild_name.content,
                tag=tag.content,
                role_id=role.id,
            )
            await ctx.send("Nuevo gremio añadido.")
        else:
            await ctx.send("Rol no encontrado.")
    elif str(reaction.emoji) == "2️⃣":
        if not configs:
            await ctx.send("No hay gremios configurados para eliminar.")
            await mostrar_menu(ctx)
            return

        # Enumerar gremios con números y emojis
        msg = "Selecciona el gremio que deseas eliminar:\n"
        emojis = []
        for i, config in enumerate(configs):
            msg += f"{i+1}️⃣ {config['guild_name']}\n"
            emojis.append(f"{i+1}️⃣")
        msg += "0️⃣ Cancelar"
        emojis.append("0️⃣")

        config_message = await ctx.send(msg)
        for emoji in emojis:
            await config_message.add_reaction(emoji)

        def check(reaction, user):
            return (
                user == ctx.author
                and str(reaction.emoji) in emojis
                and reaction.message.id == config_message.id
            )

        reaction, user = await bot.wait_for("reaction_add", check=check)

        if str(reaction.emoji) == "0️⃣":
            await ctx.send("Cancelado.")
            await mostrar_menu(ctx)
            return

        index = int(emojis.index(str(reaction.emoji)))
        eliminar_gremio(guild_discord_id, configs[index]["guild_name"])
        await ctx.send(f'Gremio *{configs[index]["guild_name"]}* eliminado.')

    elif str(reaction.emoji) == "✅":
        await ctx.send("Configuración finalizada.")
        return

    await ctx.send("Configuración actualizada.")
    await mostrar_menu(ctx)


@bot.event
async def on_ready():
    print(f"Bot {bot.user} está listo.")
    monitorizar_gremios.start()


@bot.command()
@commands.has_permissions(manage_messages=True)
async def c(ctx):
    await mostrar_menu(ctx)


@c.error
async def c_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(
            "No tienes permisos suficientes para ejecutar este comando. Se requiere el permiso de Moderador."
        )


async def buscar_usuario_albion(usuario, intentos=3, timeout=10):
    usuario = usuario.split("] ")[-1]  # Ajustar el nombre del usuario
    url = f"https://gameinfo.albiononline.com/api/gameinfo/search?q={usuario}"
    for i in range(intentos):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=timeout) as response:
                    if response.status == 200:
                        return await response.json()
        except asyncio.TimeoutError:
            if i < intentos - 1:
                continue
            else:
                raise
        except aiohttp.ClientError as e:
            raise e


@bot.command(name="u")
async def plus(ctx, *, usuario: str):
    guild_id = ctx.guild.id
    configs = cargar_configuraciones(guild_id)

    if not configs:
        await ctx.send(
            "Por favor, configura al menos un gremio primero usando el comando !c."
        )
        return

    try:
        data = await buscar_usuario_albion(usuario)
    except asyncio.TimeoutError:
        await ctx.send(
            f"No se pudo obtener la información para el usuario *{usuario}* debido a un tiempo de espera. Inténtalo nuevamente más tarde."
        )
        return
    except aiohttp.ClientError as e:
        await ctx.send(
            f"Ocurrió un error al buscar los datos para el usuario *{usuario}*: {e}. Por favor, intenta nuevamente más tarde."
        )
        return

    if data.get("players"):
        player_data = None
        for player in data["players"]:
            if player.get("Name", "").lower() == usuario.lower():
                for config in configs:
                    if player.get("GuildName") == config["guild_name"]:
                        player_data = player
                        break
                if player_data:
                    break

        if player_data:
            player_id = player_data["Id"]  # noqa: F841
            player_name = player_data["Name"]
            player_guild = player_data["GuildName"]

            member = discord.utils.get(ctx.guild.members, id=ctx.author.id)
            if member:
                for config in configs:
                    if member.display_name.startswith(config["tag"]):
                        await ctx.send(
                            f"Ya estás registrado en el gremio *{player_guild}*."
                        )
                        return

                new_nickname = f"{config['tag']} {player_name}".strip()
                role = discord.utils.get(ctx.guild.roles, id=config["role_id"])
                if role:
                    await member.edit(nick=new_nickname)
                    await member.add_roles(role)
                else:
                    await ctx.send(
                        f"Rol no encontrado para el gremio *{player_guild}*."
                    )

            embed = discord.Embed(
                title=f"🎉 *¡Bienvenido a {player_guild}, {player_name}!* 🎉",
                color=discord.Color.green(),
            )
            await ctx.send(embed=embed)

        else:
            await ctx.send(
                f"No se encontró al usuario *{usuario}* en el gremio configurado. Verifica que el nombre esté correcto o que el usuario sea parte del gremio."
            )
    else:
        await ctx.send(
            f"No se encontró al usuario *{usuario}* en el gremio configurado. Verifica que el nombre esté correcto o que el usuario sea parte del gremio."
        )


@tasks.loop(minutes=50)
async def monitorizar_gremios():
    for guild_id in [g.id for g in bot.guilds]:
        configs = cargar_configuraciones(guild_id)
        guild = bot.get_guild(guild_id)
        if not guild:
            continue

        for config in configs:
            role = discord.utils.get(guild.roles, id=config.get("role_id"))
            if role:
                for member in guild.members:
                    if role in member.roles and not member.display_name.startswith(
                        config.get("tag")
                    ):
                        await member.remove_roles(role)
                        await member.edit(nick=None)


bot.run(os.getenv("DISCORD_BOT_TOKEN"))
