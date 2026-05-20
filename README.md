# collectibles-ballsdex

### (THIS IS NOT A COPY OF faye69's COLLECTOR CARD PACKAGE. If you're looking for that package, it's right [here](https://github.com/faye69/BallsDex-Collector-Pack/tree/main))

Extra collectibles for your dex! Utilizes currency for purchasing collectibles and also tracks many things like ball count, shinies and special balls for extra challenges. Players can view all their collectibles in their completion.

## Installing
1. Write this inside `config/extra.toml`, You can change the command_group_name to something else if you want a cooler name, or one that matches your dex! (My dex uses "charms")
   ```toml
   [[ballsdex.packages]]
   location = "git+https://github.com/CrashTestAlex/collectibles-ballsdex.git"
   path = "collect"
   enabled = true
   editable = false

   ```
2. Rebuild your bot
   ```
   docker compose build
   docker compose up
   ```
   
## Commands & Features
| Command | Description |
|---|---|
| `/collectible store` | You can shop for the collectibles here. This has all the info, stats and requirements for each collectible! Very easy to navigate and purchase. |
| `/collectible completion` | Its in the name, view what collectibles you DO have and view your missing ones. |

## Notes
- Again, this isnt a copy of the collector card package. The link for it is embedded at the top of this markdown
- There is a preloaded test charm that comes when you install this package. If no charms are in the database the shop command doesnt work.
- Make sure there is a way for players to obtain currency, otherwise this package is useless! If you want to find packages that work with currency you can join the [BallsDex Developers Server](https://discord.gg/TJQ2evaDBW) to find custom packages, or wait for me to release more!
- If you wish to edit the name of "Collectibles" into something else edit the preloaded GroupName model to make it something else
