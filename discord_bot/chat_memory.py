# just functions from the original discord_bot.py -file
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

