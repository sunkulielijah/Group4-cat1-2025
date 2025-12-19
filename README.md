system architeture

┌─────────────────────────────────────────────┐
│           COORDINATOR (Port 5000)           │
│          (Interactive Command Line)         │
└─────────────────┬───────────────────────────┘
                  │
    ┌─────────────┼─────────────┐
    │             │             │
    ▼             ▼             ▼
┌─────────┐  ┌─────────┐  ┌─────────┐
│ NODE-1  │  │ NODE-2  │  │ NODE-3  │
│ Port 6001│  │ Port 6002│  │ Port 6003│
│ ACC001  │  │ ACC003  │  │ ACC005  │
│ ACC002  │  │ ACC004  │  │ ACC006  │
└─────────┘  └─────────┘  └─────────┘

Account Distribution
NODE-1: ACC001 ($1000), ACC002 ($2000)

NODE-2: ACC003 ($1500), ACC004 ($3000)

NODE-3: ACC005 ($500), ACC006 ($1000)

Quick Start
##Step 1: Download the Code
bash
# Clone or download distributed_system.py
# Ensure you have only one file: distributed_system.py
##Step 2: Open 4 Terminal Windows
You'll need four separate terminal windows/tabs for:

Coordinator

Node 1

Node 2

Node 3

##Step 3: Start the System
Terminal 1 - Coordinator:
bash
python distributed_system.py coordinator

Terminal 2 - Node 1:
bash
python distributed_system.py node NODE-1

Terminal 3 - Node 2:
bash
python distributed_system.py node NODE-2

Terminal 4 - Node 3:
bash
python distributed_system.py node NODE-3

#Windows Users
Open 4 Command Prompt or PowerShell windows

Navigate to the project directory in each window

Run the commands above

#macOS/Linux Users
Open 4 terminal windows/tabs

Navigate to the project directory

Run the commands above



DISTRIBUTED TRANSACTION COORDINATOR

Coordinator started on localhost:5000
Waiting for nodes to register...
- Node NODE-1 registered at localhost:6001
- Node NODE-2 registered at localhost:6002
- Node NODE-3 registered at localhost:6003


#COORDINATOR COMMAND INTERFACE
Commands:
  status    - Check system status
  transfer  - Execute a single transfer
  custom    - Input MULTIPLE transactions and execute them CONCURRENTLY
  conflict  - Run forced concurrency test
  quit      - Exit
