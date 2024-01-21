#!/usr/bin/env python3
# ref: https://realpython.com/how-to-make-a-discord-bot-python/

import os
import requests
import discord
import json
import time
from dotenv import load_dotenv

ollama_server = "http://192.168.8.20"
ollama_port = "11434"
model = "llama2-uncensored:7b-chat-q6_K"
timestamp = int(time.time())
message_dictionary = {'lastupdate':timestamp, 'messages': []}

def generate_response(message):

    string_message = ""
    for json_entry in message:
        if len(string_message) == 0:
            string_message = "[" + string_message + json_entry
        else:
            string_message = string_message + "," + json_entry
    json_test = json.loads(string_message + "]")

    json_data = { "model":model, "messages": json_test, "stream": False }
    print(json_data)
    url = f"{ollama_server}:{ollama_port}/api/chat"
    print(url)
    response = requests.post(url, headers={'Accept': 'application/json'}, json=json_data)
    
    if response.status_code != 200:
        return "Back end missing"
    else:
        data = json.loads(response.text)
        return_value = data['message']['content']
        print(f"Response value is {return_value}")
        return return_value

def check_message_history():
    """
    Function that returns message history array, which can be empty
    """

    # if the timestamp is more than 15 minutes old, make the dictionary to be
    # just the timestamp
    now = int(time.time())
    if (now - message_dictionary['lastupdate']) > 900:
        message_dictionary['lastupdate'] = now
        print ("Message history is old, dumped it")
        return []
    else:
        return message_dictionary["messages"]
        


load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'{client.user} has connected to Discord!')

@client.event
async def on_message(message):
    print("Saw a message")
    if message.author == client.user:
        return
    try:
        # check if list message.mentions contains client.user as value
        if client.user in message.mentions:
#        if message.channel.name == "llm-ai-ml-jnpp":
            print(f"Somebody said:{message.content}")
            print(f"Generating response")
            # Getting the previous message history
            message_history = check_message_history()
            # Adding the last message to the history
            json_message = json.dumps({ "role": "user", "content": message.content })
            message_history.append(json_message)
            # Generating a response
            response = generate_response(message_history)
            # Adding the response to history
            json_message = json.dumps( {"role":"assistant", "content":response})
            message_history.append(json_message.strip())
            # if the response is over 2000 chr long, split to max 1500 chr and send in chunks
            if len(response) > 2000:
                response_array = [response[i*1500:(i+1)*1500] for i in range((len(response)//1500)+1)]
                for r in response_array:
                    await message.channel.send(r.strip())
            else:
                await message.channel.send(response.strip())
            
            # Saving the message history
                message_dictionary['lastupdate'] = int(time.time())
                message_dictionary['messages'] = message_history
    except Exception as e:
        print("Private message?")
        print(e)

client.run(TOKEN)
