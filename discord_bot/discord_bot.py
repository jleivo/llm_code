"""
This module implements a Discord bot that interacts with users and generates 
responses using a language model.
Functions:
    generate_response(message):
        Generates a response to the message using a language model.
    check_message_history(author):
        Checks and returns the message history for a given author if it is younger than 15 minutes.
    extract_urls(message):
        Extracts URLs from a given message.
    send_response(message, reply):
        Sends a response back to the Discord channel, chunking the message if it 
        exceeds the maximum length.
    prepare_llm_message(user_message, author):
        Prepares the input for the language model from a Discord message.
    update_history(message_history, llm_response, author):
        Adds the message to history and updates the timestamp.
    extract_text(url):
        Extracts text content from a given URL.
    respond(message, source):
        Generates a response to a message and sends it back to the Discord channel.
    check_message_commands(message, source):
        Checks the message for various commands and executes them if found.
    clear_history(source):
        Clears the message history for a given source and updates the timestamp.
Discord Bot Events:
    on_ready():
        Event handler for when the bot has connected to Discord.
    on_message(message):
        Event handler for when a message is received.
"""
# ref: https://realpython.com/how-to-make-a-discord-bot-python/

#!/usr/bin/env python3
import os
import requests
import discord
import asyncio
import json
import time
import re
from bs4 import BeautifulSoup
from dotenv import load_dotenv

############################### Ollama configs ################################
ollama_server = "http://ollama.intra.leivo"
ollama_port = 11434
ollama_timeout = 120
model = "lunatic-leivo-model"
modelctx = "16384"
###############################################################################
debug = False
max_history_age = 900 # 15 minutes, defines message memory duration in time
page_load_timeout = 10 # Timeout for downloading a page
timestamp = int(time.time())
author_message = {"lastupdate":timestamp, "messages": []}
# Dictionary where the key is the author/source and value is author_message dictionary
message_dictionary = {}

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
    json_message = json.loads(string_message + "]")
    json_message = { "model": model, "messages": json_message, "stream": False,
                 "options": { "num_ctx": modelctx } }

    url = f"{ollama_server}:{ollama_port}/api/chat"
    response = requests.post(url, headers={"Accept": "application/json"},
                             json=json_message, timeout=ollama_timeout)

    if response.status_code != 200:
        return "Back end missing"
    else:
        data = json.loads(response.text)
        return_value = data["message"]["content"]
        print(f"Response value is {return_value}")
        return return_value

def check_message_history(author):
    """Check and return message history, if any.

    Function checks if the chat history is younger than 15 minutes.
    If it is, it returns it, otherwise it returns an empty list and
    resets the chat history.

    Returns:
        list: Zero or more JSON strings in a list
    """
    now = int(time.time())
    if message_dictionary.get(author) is None:
        return []
    author_message_dictionary = message_dictionary.get(author)
    if (now - author_message_dictionary["lastupdate"]) > max_history_age:
        author_message_dictionary["lastupdate"] = now
        if debug:
            print ("Message history is old, dumped it")
        return []
    else:
        return author_message_dictionary["messages"]

def extract_urls(message):
    """Extract URLS from given message

    Args:
        message (string): Chat message from Discord

    Returns:
        string: URL's if any in the message
    """
    pattern = r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
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
    max_message_length = 1800

    if len(reply) > max_message_length:
        response_array = [reply[i*max_message_length:(i+1)*max_message_length] \
                          for i in range((len(reply)//max_message_length)+1)]
        for reply_chunk in response_array:
            await message.channel.send(reply_chunk.strip())
    else:
        await message.channel.send(reply.strip())

def prepare_llm_message(user_message,author):
    """Prepare LLM input for the model from a Discord message

    Function gets the message history and allows us to develop
    further intelligence related to the message. 

    Args:
        user_message (string): The message from the user
        author (string): The source of the message
    
    Returns:
        list: List of JSON strings in a list
    """

    page_content = ""

    urls = extract_urls(user_message)
    if debug: print(urls)
    if urls:
        print("There is a URL!")
        for url in urls:
            page_content = page_content + (extract_text(url)).strip()
        user_message = user_message + "here is the content of the URL:" + page_content

    message_history = check_message_history(author)
    json_message = json.dumps({ "role": "user", "content": user_message })
    message_history.append(json_message)

    return message_history

def update_history(message_history, llm_response, author):
    """Adds the message to history and updates time stamp

    Args:
        llm_message (string): The response from the LLM
    """
    author_message_dictionary = {}

    json_message = json.dumps( {"role":"assistant", "content":llm_response})
    message_history.append(json_message.strip())
    author_message_dictionary["lastupdate"] = int(time.time())
    author_message_dictionary["messages"] = message_history
    message_dictionary[author] = author_message_dictionary

def extract_text(url):
    """Extracting the text from the URL

    Code is generated by Phi2.7

    Args:
        url (string): URL to extract contents from

    Returns:
        string: Text from the page
    """
    response = requests.get(url,timeout=page_load_timeout)
    if response.status_code != 200:
        return "Could not load the page"
    soup = BeautifulSoup(response.text, "html.parser")

    for script in soup(["script", "style"]): # remove all javascript and stylesheet code
        script.extract()

    # Clean up the text, remove extra spaces and empty lines
    text = soup.get_text()
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = "\n".join(chunk for chunk in chunks if chunk)

    return text

async def respond(message,source):
    """Function to generate response back to the message

    Args:
        message (object): The full message from Discord

    """
    print("Generating response")
    llm_message = prepare_llm_message(message.content,source)
    llm_response = generate_response(llm_message)
    task = asyncio.create_task(send_response(message, llm_response))
    await task
    # Adding the response to history
    update_history(llm_message,llm_response,source)

def check_message_commands(message,source):
    """Checks the first words of the message for various commands.
    if commands were found function executes the commands and returns
    true. If commands were not found it returns false.

    Args:
        message (object): Discord message object (or is it actually a dictionary...)
    """
    command = ""
    # Depending on which type of chat we have the first or the second word is the command.
    # ie. were we called by name or was this a private chat.
    if len(message.content.split()) > 2:
        command = message.content.split()[1]
    else:
        command = message.content.split()[0]

    if "forget" in command:
        clear_history(source)
        return True

    return False

def clear_history(source):
    """Clean up message history and update the timestamp to be this very moment

    Args:
        source (string): The chat history string string to clean
    """
    author_message_dictionary = {}

    author_message_dictionary["lastupdate"] = int(time.time())
    author_message_dictionary["messages"] = []
    message_dictionary[source] = author_message_dictionary
    print(f"Cleaned history for {source}")


# copy-paste code from real python articke
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Fixed with the help of CodeLlama, article was behind on times
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"{client.user} has connected to Discord!")

@client.event
async def on_message(message):
    if debug: print("Saw a message")
    if message.author == client.user:
        return
    try:
        # check if list message.mentions contains client.user as value
        if client.user in message.mentions:
            if debug: print(f"Somebody said to me:{message.content}")
            source = message.channel
            if check_message_commands(message,source):
                if debug: print("Ran command...")
            else:
                task = asyncio.create_task(respond(message,source))
                await task
    except Exception as e: # pylint: disable=broad-exception-caught
        print("Unknown thing?")
        print(e)
    # Lets see if its a private chat?
    if isinstance(message.channel, discord.DMChannel):
        source = message.author
        if check_message_commands(message,source):
            if debug: print("Ran a command...")
        else:
            task = asyncio.create_task(respond(message,source))
            await task

client.run(TOKEN)
