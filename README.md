# Distributed Transaction System (2PC Simulation)

A simple **distributed transaction system** demonstrating **Two-Phase Commit (2PC)** with concurrency, failure handling, and recovery using a **single Python file**.

The system consists of **one Coordinator** and **three Participant Nodes**, communicating over TCP sockets and coordinated via an interactive command-line interface.

---

##  System Architecture

```
┌─────────────────────────────────────────────┐
│           COORDINATOR (Port 5000)           │
│          Interactive Command Line           │
└─────────────────┬───────────────────────────┘
                  │
    ┌─────────────┼─────────────┐
    │             │             │
    ▼             ▼             ▼
┌─────────┐  ┌─────────┐  ┌─────────┐
│ NODE-1  │  │ NODE-2  │  │ NODE-3  │
│ Port6001│  │ Port6002│  │ Port6003│
│ ACC001  │  │ ACC003  │  │ ACC005  │
│ ACC002  │  │ ACC004  │  │ ACC006  │
└─────────┘  └─────────┘  └─────────┘
```

---

##  Account Distribution

| Node   | Accounts                       |
| ------ | ------------------------------ |
| NODE-1 | ACC001 ($1000), ACC002 ($2000) |
| NODE-2 | ACC003 ($1500), ACC004 ($3000) |
| NODE-3 | ACC005 ($500), ACC006 ($1000)  |

---

##  Quick Start

### Step 1: Download the Code

Ensure you have **only one file**:

```
script.py
```

You may clone or copy the file into a new project directory.

---

### Step 2: Open 4 Terminal Windows

You will need **four separate terminals**:

1. Coordinator
2. Node 1
3. Node 2
4. Node 3

---

### Step 3: Start the System

#### Terminal 1 – Coordinator

```bash
python script.py coordinator
```

#### Terminal 2 – Node 1

```bash
python script.py node NODE-1
```

#### Terminal 3 – Node 2

```bash
python script.py node NODE-2
```

#### Terminal 4 – Node 3

```bash
python script.py node NODE-3
```

---

## 🪟 Platform Notes

### Windows Users

* Open **4 Command Prompt or PowerShell** windows
* Navigate to the project directory in each window
* Run the commands above

### macOS / Linux Users

* Open **4 terminal windows or tabs**
* Navigate to the project directory
* Run the commands above

---

##  Coordinator Startup Output

Once all nodes register successfully, you should see:

```
DISTRIBUTED TRANSACTION COORDINATOR

Coordinator started on localhost:5000
Waiting for nodes to register...
- Node NODE-1 registered at localhost:6001
- Node NODE-2 registered at localhost:6002
- Node NODE-3 registered at localhost:6003
```

---

##  Coordinator Command Interface

The coordinator provides an **interactive CLI** with the following commands:

```
Commands:
  status    - Check system status
  transfer  - Execute a single transfer
  custom    - Input MULTIPLE transactions and execute them CONCURRENTLY
  conflict  - Run forced concurrency test
  quit      - Exit
```

---

##  Features Demonstrated

* Two-Phase Commit (2PC)
* Distributed transaction coordination
* Lock-based concurrency control
* Concurrent transaction execution
* Failure and recovery handling
* Atomicity and consistency guarantees

---

