from discord.ext import commands
from .utils import config, checks, maps
import asyncio, aiohttp
from urllib.parse import quote as urlquote
import random

class Splatoon:
    """Splatoon related commands."""

    def __init__(self, bot):
        self.bot = bot
        self.config = config.Config('splatoon.json', loop=bot.loop)
        self.map_data = []
        self.map_updater = bot.loop.create_task(self.update_maps())

    def __del__(self):
        self.map_updater.cancel()

    async def update_maps(self):
        username = self.config.get('username')
        password = self.config.get('password')
        try:
            while not self.bot.is_closed:
                await self.update_schedule(username, password)
                await asyncio.sleep(120) # task runs every 2 minutes
        except asyncio.CancelledError:
            pass

    async def update_schedule(self, username, password):
        try:
            cookie = await maps.get_new_splatnet_cookie(username, password)
            schedule = await maps.get_splatnet_schedule(cookie)
        except:
            # if we get an exception, keep the old data
            # make sure to remove the old data that already ended
            self.map_data = [data for data in self.map_data if not data.is_over]
        else:
            self.map_data = []
            for entry in schedule:
                if entry.is_over:
                    continue
                self.map_data.append(entry)

    def get_map_message(self, index):
        try:
            return str(self.map_data[index])
        except IndexError:
            return 'No map data found. Try again later.'

    @commands.command(hidden=True)
    async def refreshmaps(self):
        """Force refresh the maps in the rotation."""
        username = self.config.get('username')
        password = self.config.get('password')
        await self.update_schedule(username, password)

    @commands.command(aliases=['rotation'])
    async def maps(self):
        """Shows the current maps in the Splatoon schedule."""
        await self.bot.say(self.get_map_message(0))

    @commands.command(hidden=True)
    async def nextmaps(self):
        """Shows the next maps in the Splatoon schedule."""
        await self.bot.say(self.get_map_message(1))

    @commands.command(hidden=True)
    async def lastmaps(self):
        """Shows the last maps in the Splatoon schedule."""
        await self.bot.say(self.get_map_message(2))

    @commands.command()
    async def schedule(self):
        """Shows the current Splatoon schedule."""
        if self.map_data:
            await self.bot.say('\n'.join(map(str, self.map_data)))
        else:
            await self.bot.say('No map data found. Try again later.')

    def weapon_to_string(self, weapon):
        return '{0[name]}, Sub: {0[sub]}, Special: {0[special]}'.format(weapon)

    @commands.command()
    async def weapon(self, *, query : str):
        """Displays weapon info from a query.

        The query must be at least 3 characters long, otherwise it'll tell you it failed.

        If 15 or more weapons are found then the results will be PMed to you instead.
        """
        query = query.strip().lower()
        weapons = self.config.get('weapons', [])
        if len(query) < 3:
            await self.bot.say('The query must be at least 3 characters long.')
            return

        def predicate(weapon):
            lowered = [weapon.lower() for weapon in weapon.values()]
            return any(query in wep for wep in lowered)

        result = list(filter(predicate, weapons))
        if not result:
            await self.bot.say('Sorry. The query "{}" returned nothing.'.format(query))
            return

        output = ['Found {} weapon(s):'.format(len(result))]
        output.extend(self.weapon_to_string(weapon) for weapon in result)

        if len(result) > 15:
            await self.bot.whisper('\n'.join(output))
        else:
            await self.bot.say('\n'.join(output))

    @commands.command(invoke_without_command=True)
    async def scrim(self, games=5):
        """Generates scrim map and mode combinations.

        The mode combinations do not have Turf War. The number of games must
        be between 3 and 15.
        """

        maps = self.config.get('maps', [])
        modes = ['Rainmaker', 'Splat Zones', 'Tower Control']
        result = []
        games = max(min(games, 15), 3)

        for game in range(games):
            stage = random.choice(maps)
            mode = random.choice(modes)
            result.append('{} on {}'.format(mode, stage))

        await self.bot.say('\n'.join(result))

    @commands.group(invoke_without_command=True)
    async def brand(self, *, query : str):
        """Shows brand info based on either the name or the ability given.

        If the query is an ability then it attempts to find out what brands
        influence that ability, otherwise it just looks for the brand being given.

        The query must be at least 2 characters long.
        """
        query = query.strip().lower()

        if len(query) < 2:
            await self.bot.say('The query must be at least 5 characters long.')
            return

        brands = self.config.get('brands', [])

        # First, attempt to figure out if it's a brand name.
        def first_check(data):
            lowered = data['name'].lower()
            return query in lowered

        def second_check(data):
            buffed = data['buffed']
            nerfed = data['nerfed']
            if buffed is None or nerfed is None:
                return False
            return query in buffed.lower() or query in nerfed.lower()

        result = list(filter(first_check, brands))
        output = []
        fmt = 'The brand "{}" has buffed {} and nerfed {} probabilities.'
        if result:
            # brands found
            output.append('Found the following brands:')
            for entry in result:
                name = entry['name']
                buffed = entry['buffed']
                nerfed = entry['nerfed']

                if buffed is None or nerfed is None:
                    output.append('The brand "{}" is neutral.'.format(name))
                    continue

                output.append(fmt.format(name, buffed, nerfed))
            output.append('')

        abilities = list(filter(second_check, brands))
        if abilities:
            output.append('Found the following relevant abilities:')
            for entry in abilities:
                output.append(fmt.format(entry['name'], entry['buffed'], entry['nerfed']))

        if not output:
            await self.bot.say('Your query returned nothing.')
        else:
            await self.bot.say('\n'.join(output))


    @brand.command(name='list')
    async def _list(self):
        """Lists all Splatoon brands."""
        brands = self.config.get('brands', [])
        max_name = max(len(b['name']) for b in brands)
        max_ability = max(len(b['buffed']) if b['buffed'] else 4 for b in brands)
        output = ['```']
        tmp = { 'name': 'Brand', 'nerfed': 'Nerfed', 'buffed': 'Buffed' }
        fmt = '{0[name]!s:<{n}} {0[buffed]!s:<{a}} {0[nerfed]!s:<{a}}'
        output.append(fmt.format(tmp, n=max_name, a=max_ability))
        output.append('-' * (max_name + max_ability * 2))

        for brand in brands:
            output.append(fmt.format(brand, n=max_name, a=max_ability))
        output.append('```')
        await self.bot.say('\n'.join(output))

    @commands.command(hidden=True)
    async def marie(self):
        """A nice little easter egg."""
        await self.bot.say('http://i.stack.imgur.com/0OT9X.png')

    @commands.group(hidden=True)
    async def conf(self):
        """Edits the config file"""
        pass

    @conf.group()
    async def add(self):
        """Adds an entry to the config file."""
        pass

    @add.command(name='weapon')
    @checks.is_owner()
    async def add_wep(self, name, sub, special):
        """Adds a weapon to the config file."""
        weapons = self.config.get('weapons', [])
        entry = {
            'name': name,
            'sub': sub,
            'special': special
        }
        weapons.append(entry)
        await self.config.put('weapons', weapons)
        await self.bot.say('\U0001f44c')

    @add.command(name='map')
    @checks.is_owner()
    async def _map(self, name):
        """Adds a map to the config file."""
        entry = self.config.get('maps', [])
        entry.append(name)
        await self.config.put('maps', entry)
        await self.bot.say('\U0001f44c')

    @commands.command()
    async def splatwiki(self, *, title : str):
        """Returns a Inkipedia page."""
        url = 'http://splatoonwiki.org/wiki/Special:Search/' + urlquote(title)

        async with aiohttp.get(url) as resp:
            if 'Special:Search' in resp.url:
                await self.bot.say('Could not find your page. Try a search:\n{0.url}'.format(resp))
            elif resp.status == 200:
                await self.bot.say(resp.url)
            elif resp.status == 502:
                await self.bot.say('It seems that Inkipedia is taking too long to respond. Try again later.')
            else:
                await self.bot.say('An error has occurred of status code {0.status} happened. Tell Danny.'.format(resp))

def setup(bot):
    bot.add_cog(Splatoon(bot))
