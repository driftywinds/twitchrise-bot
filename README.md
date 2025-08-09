## Twitchrise Bot for Telegram - Notifications for Twitch Channels going live or offline

This is a narrowed down version of my other general use project [Twitchrise](https://github.com/driftywinds/twitchrise) for the express use as an interactive bot on Telegram.

This project iams to make one bot for multiple users, where Twitchrise uses an ```.env``` to define variables and is only catered for a single user running the script for themselves. Running one instance of this bot multiple users can: -

- Add channel to monitor (```/add <channelname>```)
- Remove channels to monitor (```/remove <channelname>```)
- List all the channels they have added to monitor (```/list```)
- Add additional Apprise endpoints (```/setapprise <URL>```)
- Remove added Apprise endpoints (```/rmapprise <number>```)
- List added Apprise endpoints (```/listapprise```)

Apprise endpoints and their formats can be seen [here](https://github.com/caronc/apprise#supported-notifications).

The bot admin can define the interval in seconds the bot will poll Twitch to check if the channels are live or not in the ```.env``` file. Although this restricts the usage of Twitchrise primarily through Telegram, I am a fan of Telegram and use it in my workflow extensively enough to warrant this usecase. 

[![Pulls](https://img.shields.io/docker/pulls/driftywinds/twitchrise-bot.svg?style=for-the-badge)](https://img.shields.io/docker/pulls/driftywinds/twitchrise-bot.svg?style=for-the-badge)

Also available on Docker Hub - [```driftywinds/twitchrise-bot:latest```](https://hub.docker.com/repository/docker/driftywinds/twitchrise-bot/general)

### How to use: - 

1. Download the ```compose.yml``` and ```.env``` files from the repo [here](https://github.com/driftywinds/twitchrise-bot).
2. Go to [https://dev.twitch.tv/console](https://dev.twitch.tv/console) and register a new application. You can name it anything, but the client type should be ```confidential```, that will give you a client ID and client secret.
3. Customise the ```.env``` file and use the client ID and client secret from above.
4. Run ```docker compose up -d```.

<br>

You can check logs live with this command: - 
```
docker compose logs -f
```
### For dev testing: -
- have python3 installed on your machine
- clone the repo
- go into the directory and run these commands: -
```
python3 -m venv .venv
source .venv/bin/activate
pip install --no-cache-dir -r requirements.txt
```  
- configure ```.env``` variables.
- then run ```python3 bot.py```
