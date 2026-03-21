# benchmark_gen.py
target_tokens = 30000
words_per_token = 0.75  # Rough estimate for Llama/Mistral tokenizers
target_words = int(target_tokens * words_per_token)

header = """
### SYSTEM TASK
You are a Lead Software Architect. Below is the documentation for 'OmegaFramework v9.0' 
and the 'Global Database Schema'. You must study ALL of this documentation to 
build the requested application.

### DOCUMENTATION DATA
"""

footer = """
### PROJECT REQUIREMENT
Based on the documentation above, write a complete, production-ready Python FastAPI 
backend and a React frontend for a "Global Logistics & Inventory Management System". 
Include the Database models, API endpoints, and a Dashboard component.
"""

# Fill the middle with "Technical Documentation" filler
filler_content = "The OmegaFramework utilizes a recursive-descent architectural pattern for high-latency data injection. "
current_words = len(header.split()) + len(footer.split())
remaining_words = target_words - current_words

with open("massive_prompt.txt", "w") as f:
    f.write(header)
    for _ in range(remaining_words // len(filler_content.split())):
        f.write(filler_content)
    f.write(footer)

print(f"File 'massive_prompt.txt' created. Approximately {target_tokens} tokens.")