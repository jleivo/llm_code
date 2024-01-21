#!/usr/bin/env python3
# ref: https://realpython.com/how-to-make-a-discord-bot-python/

import os
import requests
import discord
import asyncio
import json
import time
import re

from dotenv import load_dotenv

ollama_server = "http://192.168.8.20"
ollama_port = "11434"
model = "llama2-uncensored:7b-chat-q6_K"
timestamp = int(time.time())
message_dictionary = {'lastupdate':timestamp, 'messages': []}

def generate_response(message):
    """Generate response to the message with an LLM

    Args:
        message (list): Should contain a list of JSON strings that are in 
                        chat format
    Returns:
        String: Pure response string from LLM model. If the model is missing
                response value is "Back end missing"
    """

    # An ugly hack to generate correct looking JSON for the backend
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
    """Check and return message history, if any.

    Function checks if the chat history is younger than 15 minutes.
    If it is, it returns it, otherwise it returns an empty list and
    resets the chat history.

    Returns:
        list: Zero or more JSON strings in a list
    """
    max_history_age = 900

    # if the timestamp is more than 15 minutes old, make the dictionary to be
    # just the timestamp
    now = int(time.time())
    if (now - message_dictionary['lastupdate']) > max_history_age:
        message_dictionary['lastupdate'] = now
        print ("Message history is old, dumped it")
        return []
    else:
        return message_dictionary["messages"]

def extract_urls(message):
    """Extract URLS from given message

    Args:
        message (string): Chat message from Discord

    Returns:
        string: URL's if any in the message
    """
    pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    urls = re.findall(pattern, message)
    return urls

async def send_response(message, reply):
    """Sending the message back to the channel

    Response is chunked to max_length character pieces if it is longer
    than max_length characters. Discord limit is 2000

    Args:
        message (object): The original Discord message object
        reply (string): String
    """
    max_length = 1800

    if len(reply) > max_length:
        response_array = [reply[i*max_length:(i+1)*max_length] \
                          for i in range((len(reply)//max_length)+1)]
        for reply_chunk in response_array:
            await message.channel.send(reply_chunk.strip())
    else:
        await message.channel.send(reply.strip())

def prepare_llm_message(user_message):
    """Prepare LLM input for the model from a Discord message

    Function gets the message history and allows us to develop
    further intelligence related to the message. 

    Args:
        user_message (string): The message from the user
    
    Returns:
        list: List of JSON strings in a list
    """
    message_history = check_message_history()
    json_message = json.dumps({ "role": "user", "content": user_message })
    message_history.append(json_message)

    return message_history


def update_history(message_history, llm_response):
    """Adds the message to history and updates time stamp

    Args:
        llm_message (string): The response from the LLM
    """
    json_message = json.dumps( {"role":"assistant", "content":llm_response})
    message_history.append(json_message.strip())
    message_dictionary['lastupdate'] = int(time.time())
    message_dictionary['messages'] = message_history


# copy-paste code from real python articke
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Fixed with the help of CodeLlama, article was behind on times
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
            print(f"Somebody said to me:{message.content}")
            print("Generating response")

            # Getting the previous message history
            llm_message = prepare_llm_message(message.content)
            # Generating a response
            llm_response = generate_response(llm_message)
            # Talking back to the channel
            task = asyncio.create_task(send_response(message, llm_response))
            await task
            # Adding the response to history
            update_history(llm_message,llm_response)

    except Exception as e:
        print("Private message?")
        print(e)

client.run(TOKEN)
