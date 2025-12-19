# distributed_system.py - Run this in all terminals with different modes
import socket
import json
import threading
import time
import uuid
import sys
import random
from datetime import datetime
from typing import Dict, List, Optional

# ========== COMMON DATA STRUCTURES ==========

class Account:
    def __init__(self, account_id: str, balance: float):
        self.id = account_id
        self.balance = balance
        self.lock = threading.Lock()
        self.transaction_log = []
    
    def __str__(self):
        return f"{self.id}: ${self.balance:.2f}"

class DistributedTransaction:
    def __init__(self, transaction_id: str, from_account: str, to_account: str, amount: float):
        self.id = transaction_id
        self.from_account = from_account
        self.to_account = to_account
        self.amount = amount
        self.status = "PENDING"
        self.timestamp = datetime.now()
        self.votes = {}
        self.locks_acquired = False

# ========== COORDINATOR MODE ==========

class Coordinator:
    def __init__(self, host='localhost', port=5000):
        self.host = host
        self.port = port
        self.nodes = {}  # node_id: (host, port)
        self.transactions = {}
        self.lock = threading.Lock()
        self.running = True
        
        print(f"🎯 Coordinator initialized on {host}:{port}")
    
    def register_node(self, node_id: str, node_host: str, node_port: int):
        """Register a participant node"""
        with self.lock:
            self.nodes[node_id] = (node_host, node_port)
            print(f"✅ Node {node_id} registered at {node_host}:{node_port}")
            return True
    
    def send_to_node(self, node_id: str, message: dict) -> dict:
        """Send message to a specific node"""
        if node_id not in self.nodes:
            return {"status": "ERROR", "message": f"Node {node_id} not registered"}
        
        host, port = self.nodes[node_id]
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(3)
                s.connect((host, port))
                s.sendall(json.dumps(message).encode())
                response = s.recv(4096)
                return json.loads(response.decode())
        except Exception as e:
            print(f"❌ Failed to contact Node {node_id}: {e}")
            return {"status": "ERROR", "message": str(e)}
    
    def broadcast(self, message: dict, exclude: str = None) -> Dict[str, dict]:
        """Broadcast message to all nodes"""
        responses = {}
        for node_id in list(self.nodes.keys()):
            if exclude and node_id == exclude:
                continue
            responses[node_id] = self.send_to_node(node_id, message)
        return responses
    
    def find_account_nodes(self, from_account: str, to_account: str) -> Dict[str, list]:
        """Find which nodes contain the accounts"""
        account_nodes = {}
        
        for node_id in self.nodes:
            response = self.send_to_node(node_id, {
                "type": "CHECK_ACCOUNTS",
                "accounts": [from_account, to_account]
            })
            
            if response.get("status") == "OK":
                node_accounts = response.get("accounts", [])
                if node_accounts:
                    account_nodes[node_id] = node_accounts
        
        return account_nodes
    
    def execute_transaction(self, from_account: str, to_account: str, amount: float) -> dict:
        """Execute distributed transaction using 2-Phase Commit"""
        transaction_id = f"TXN-{uuid.uuid4().hex[:8]}"
        
        print(f"\n{'='*60}")
        print(f"🚀 INITIATING TRANSACTION {transaction_id}")
        print(f"💸 Transfer: ${amount:.2f} from {from_account} to {to_account}")
        print(f"{'='*60}")
        
        # Find which nodes have the accounts
        account_nodes = self.find_account_nodes(from_account, to_account)
        
        if not account_nodes:
            return {"status": "ERROR", "message": "Accounts not found in any node"}
        
        # PHASE 1: PREPARE
        print("\n📋 PHASE 1: PREPARING TRANSACTION")
        prepare_results = {}
        
        for node_id, accounts in account_nodes.items():
            prepare_msg = {
                "type": "PREPARE",
                "transaction_id": transaction_id,
                "from_account": from_account,
                "to_account": to_account,
                "amount": amount,
                "accounts": accounts
            }
            
            response = self.send_to_node(node_id, prepare_msg)
            prepare_results[node_id] = response
            print(f"  Node {node_id}: {response.get('status', 'ERROR')} - {response.get('message', '')}")
        
        # Check if all nodes prepared successfully
        all_prepared = all(r.get("status") in ["PREPARED", "NO_ACCOUNTS"] for r in prepare_results.values())
        
        if not all_prepared:
            print("\n⚠️  Transaction Aborted: Prepare phase failed")
            print("🔄 Initiating Rollback...")
            
            # Rollback on all nodes
            self.broadcast({
                "type": "ROLLBACK",
                "transaction_id": transaction_id
            })
            
            self.transactions[transaction_id] = {
                "status": "ABORTED",
                "reason": "Prepare phase failed",
                "prepare_results": prepare_results
            }
            
            return {
                "status": "ABORTED",
                "transaction_id": transaction_id,
                "message": "Transaction failed during prepare phase"
            }
        
        # PHASE 2: COMMIT
        print("\n📋 PHASE 2: COMMITTING TRANSACTION")
        commit_msg = {
            "type": "COMMIT",
            "transaction_id": transaction_id
        }
        
        commit_results = self.broadcast(commit_msg)
        
        successful = sum(1 for r in commit_results.values() if r.get("status") == "COMMITTED")
        total = len(commit_results)
        
        if successful == total:
            print(f"\n🎉 TRANSACTION {transaction_id} SUCCESSFULLY COMMITTED!")
            status = "COMMITTED"
        else:
            print(f"\n⚠️  PARTIAL COMMIT: {successful}/{total} nodes committed")
            print("🔧 Recovery needed for inconsistent nodes")
            status = "PARTIAL_COMMIT"
        
        # Log transaction
        self.transactions[transaction_id] = {
            "from_account": from_account,
            "to_account": to_account,
            "amount": amount,
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "prepare_results": prepare_results,
            "commit_results": commit_results
        }
        
        return {
            "transaction_id": transaction_id,
            "status": status,
            "details": self.transactions[transaction_id]
        }
    
    def simulate_concurrent_transfers(self, num_transfers: int = 4):
        """Simulate multiple concurrent transfers"""
        print(f"\n{'='*60}")
        print(f"🧪 SIMULATING {num_transfers} CONCURRENT TRANSFERS")
        print("="*60)
        
        # Create list of random transfers
        transfers = []
        account_ids = ["ACC001", "ACC002", "ACC003", "ACC004", "ACC005", "ACC006"]
        
        for _ in range(num_transfers):
            from_acc = random.choice(account_ids)
            to_acc = random.choice(account_ids)
            while to_acc == from_acc:
                to_acc = random.choice(account_ids)
            
            amount = random.uniform(10, 500)
            transfers.append((from_acc, to_acc, amount))
        
        # Execute transfers concurrently using threads
        threads = []
        results = []
        results_lock = threading.Lock()
        
        def execute_transfer_thread(from_acc: str, to_acc: str, amt: float, client_id: str):
            """Thread function to execute a single transfer"""
            print(f"\n👤 {client_id} initiating transfer: ${amt:.2f} from {from_acc} to {to_acc}")
            result = self.execute_transaction(from_acc, to_acc, amt)
            
            with results_lock:
                results.append(result)
            
            print(f"   {client_id} result: {result['status']}")
        
        # Start all threads
        for i, (from_acc, to_acc, amount) in enumerate(transfers):
            thread = threading.Thread(
                target=execute_transfer_thread,
                args=(from_acc, to_acc, amount, f"Client-{i+1}"),
                daemon=True
            )
            threads.append(thread)
            thread.start()
            time.sleep(0.1)  # Small delay to show concurrency
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join(timeout=10)
        
        # Display summary
        print(f"\n{'='*60}")
        print("📊 CONCURRENT TRANSFER RESULTS")
        print("="*60)
        
        successful = sum(1 for r in results if r.get("status") == "COMMITTED")
        print(f"Total transfers attempted: {len(transfers)}")
        print(f"Successful transfers: {successful}")
        print(f"Failed/Aborted transfers: {len(transfers) - successful}")
        
        return results
    
    def get_system_status(self) -> dict:
        """Get status of all registered nodes"""
        status = {}
        for node_id in self.nodes:
            response = self.send_to_node(node_id, {"type": "STATUS"})
            status[node_id] = response
        return status
    
    def handle_client_request(self, client_socket: socket.socket):
        """Handle incoming connection from nodes or clients"""
        try:
            data = client_socket.recv(4096)
            if data:
                message = json.loads(data.decode())
                
                if message.get("type") == "REGISTER":
                    node_id = message["node_id"]
                    node_host = message["host"]
                    node_port = message["port"]
                    
                    if self.register_node(node_id, node_host, node_port):
                        response = {"status": "REGISTERED", "node_id": node_id}
                    else:
                        response = {"status": "ERROR", "message": "Registration failed"}
                    
                    client_socket.sendall(json.dumps(response).encode())
                
                elif message.get("type") == "TRANSACTION_REQUEST":
                    from_acc = message.get("from_account")
                    to_acc = message.get("to_account")
                    amount = message.get("amount")
                    
                    result = self.execute_transaction(from_acc, to_acc, amount)
                    client_socket.sendall(json.dumps(result).encode())
                
                else:
                    response = {"status": "ERROR", "message": "Unknown request type"}
                    client_socket.sendall(json.dumps(response).encode())
        
        except Exception as e:
            print(f"Error handling client: {e}")
        finally:
            client_socket.close()
    
    def start_server(self):
        """Start the coordinator server"""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.host, self.port))
        server.listen(10)
        
        print(f"\n🎯 Coordinator server started on {self.host}:{self.port}")
        print("Waiting for nodes to register...")
        
        while self.running:
            try:
                client, address = server.accept()
                threading.Thread(
                    target=self.handle_client_request,
                    args=(client,),
                    daemon=True
                ).start()
            except Exception as e:
                if self.running:
                    print(f"Server error: {e}")
        
        server.close()
    
    def coordinator_cli(self):
        """Command Line Interface for Coordinator"""
        print("\n" + "="*60)
        print("🎮 COORDINATOR COMMAND INTERFACE")
        print("="*60)
        print("Commands:")
        print("  status      - Show system status")
        print("  transfer    - Execute a transfer")
        print("  concurrent  - Run concurrent transfers")
        print("  quit        - Exit")
        print("="*60)
        
        while True:
            try:
                cmd = input("\ncoordinator> ").strip().lower()
                
                if cmd == "status":
                    status = self.get_system_status()
                    print("\n📊 SYSTEM STATUS:")
                    for node_id, info in status.items():
                        active = "🟢 ONLINE" if info.get("active", False) else "🔴 OFFLINE"
                        print(f"  {node_id}: {active}")
                        if "accounts" in info:
                            for acc in info["accounts"]:
                                print(f"    {acc['id']}: ${acc['balance']:.2f}")
                
                elif cmd == "transfer":
                    try:
                        from_acc = input("From account: ").strip()
                        to_acc = input("To account: ").strip()
                        amount = float(input("Amount: ").strip())
                        
                        result = self.execute_transaction(from_acc, to_acc, amount)
                        print(f"\nResult: {result['status']}")
                        if result.get("transaction_id"):
                            print(f"Transaction ID: {result['transaction_id']}")
                    except ValueError:
                        print("❌ Invalid amount. Please enter a number.")
                    except Exception as e:
                        print(f"❌ Error: {e}")
                
                elif cmd == "concurrent":
                    try:
                        num = input("Number of concurrent transfers (default 4): ").strip()
                        num_transfers = int(num) if num else 4
                        self.simulate_concurrent_transfers(num_transfers)
                    except ValueError:
                        print("❌ Invalid number. Using default of 4 transfers.")
                        self.simulate_concurrent_transfers(4)
                
                elif cmd == "quit":
                    print("Shutting down coordinator...")
                    self.running = False
                    break
                
                else:
                    print("❌ Unknown command. Try: status, transfer, concurrent, quit")
            
            except KeyboardInterrupt:
                print("\n\nShutting down coordinator...")
                self.running = False
                break
            except Exception as e:
                print(f"❌ Error: {e}")

# ========== NODE MODE ==========

class ParticipantNode:
    def __init__(self, node_id: str, coordinator_host='localhost', coordinator_port=5000, node_port=6000):
        self.node_id = node_id
        self.host = 'localhost'
        self.port = node_port + int(node_id[-1])  # Different port for each node
        self.coordinator_host = coordinator_host
        self.coordinator_port = coordinator_port
        self.accounts = {}
        self.transactions = {}
        self.active = True
        self.running = True
        
        # Initialize accounts based on node ID
        self._initialize_accounts()
        
        # Register with coordinator
        self.register_with_coordinator()
    
    def _initialize_accounts(self):
        """Initialize accounts for this node"""
        if self.node_id == "NODE-1":
            self.accounts = {
                "ACC001": Account("ACC001", 1000.0),
                "ACC002": Account("ACC002", 2000.0)
            }
        elif self.node_id == "NODE-2":
            self.accounts = {
                "ACC003": Account("ACC003", 1500.0),
                "ACC004": Account("ACC004", 3000.0)
            }
        elif self.node_id == "NODE-3":
            self.accounts = {
                "ACC005": Account("ACC005", 500.0),
                "ACC006": Account("ACC006", 1000.0)
            }
        
        print(f"💰 Node {self.node_id} initialized with accounts:")
        for acc in self.accounts.values():
            print(f"  {acc}")
    
    def register_with_coordinator(self):
        """Register this node with the coordinator"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((self.coordinator_host, self.coordinator_port))
                message = {
                    "type": "REGISTER",
                    "node_id": self.node_id,
                    "host": self.host,
                    "port": self.port
                }
                s.sendall(json.dumps(message).encode())
                response = json.loads(s.recv(4096).decode())
                
                if response.get("status") == "REGISTERED":
                    print(f"✅ Successfully registered with coordinator as {self.node_id}")
                    return True
                else:
                    print(f"❌ Failed to register: {response}")
                    return False
        except Exception as e:
            print(f"❌ Cannot connect to coordinator at {self.coordinator_host}:{self.coordinator_port}")
            print(f"   Error: {e}")
            print("   Make sure coordinator is running first!")
            return False
    
    def handle_prepare(self, transaction_id: str, accounts: list, 
                      from_account: str, to_account: str, amount: float) -> dict:
        """Handle prepare phase of 2PC"""
        print(f"\n📋 [NODE {self.node_id}] PREPARE for {transaction_id}")
        
        if not self.active:
            return {"status": "ERROR", "message": "Node not active"}
        
        # Check which accounts are on this node
        local_accounts = [acc for acc in accounts if acc in self.accounts]
        
        if not local_accounts:
            return {"status": "NO_ACCOUNTS", "message": "No relevant accounts on this node"}
        
        # Try to acquire locks
        acquired_locks = []
        try:
            for acc_id in local_accounts:
                account = self.accounts[acc_id]
                if account.lock.acquire(blocking=False):
                    acquired_locks.append(acc_id)
                    print(f"  🔒 Acquired lock for {acc_id}")
                else:
                    # Release any acquired locks
                    for locked_acc in acquired_locks:
                        self.accounts[locked_acc].lock.release()
                    return {
                        "status": "ABORT",
                        "message": f"Could not acquire lock for {acc_id}"
                    }
            
            # Check balance for debit accounts
            if from_account in local_accounts:
                if self.accounts[from_account].balance < amount:
                    # Release locks
                    for acc_id in local_accounts:
                        self.accounts[acc_id].lock.release()
                    return {
                        "status": "ABORT",
                        "message": f"Insufficient funds in {from_account}"
                    }
            
            # Store transaction state
            self.transactions[transaction_id] = {
                "status": "PREPARED",
                "from_account": from_account,
                "to_account": to_account,
                "amount": amount,
                "local_accounts": local_accounts,
                "timestamp": datetime.now().isoformat()
            }
            
            return {"status": "PREPARED", "message": "Ready to commit"}
        
        except Exception as e:
            # Release locks on error
            for acc_id in local_accounts:
                if acc_id in self.accounts:
                    self.accounts[acc_id].lock.release()
            return {"status": "ERROR", "message": str(e)}
    
    def handle_commit(self, transaction_id: str) -> dict:
        """Handle commit phase of 2PC"""
        print(f"\n💾 [NODE {self.node_id}] COMMIT for {transaction_id}")
        
        if transaction_id not in self.transactions:
            return {"status": "ERROR", "message": "Transaction not found"}
        
        transaction = self.transactions[transaction_id]
        
        try:
            # Execute transfer
            if transaction["from_account"] in self.accounts:
                self.accounts[transaction["from_account"]].balance -= transaction["amount"]
                self.accounts[transaction["from_account"]].transaction_log.append(
                    f"[{datetime.now()}] Debit ${transaction['amount']:.2f} (TXN:{transaction_id})"
                )
            
            if transaction["to_account"] in self.accounts:
                self.accounts[transaction["to_account"]].balance += transaction["amount"]
                self.accounts[transaction["to_account"]].transaction_log.append(
                    f"[{datetime.now()}] Credit ${transaction['amount']:.2f} (TXN:{transaction_id})"
                )
            
            # Release locks
            for acc_id in transaction["local_accounts"]:
                self.accounts[acc_id].lock.release()
                print(f"  🔓 Released lock for {acc_id}")
            
            transaction["status"] = "COMMITTED"
            print(f"  ✅ Transaction {transaction_id} committed successfully")
            
            return {"status": "COMMITTED", "message": "Transaction committed"}
        
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}
    
    def handle_rollback(self, transaction_id: str) -> dict:
        """Handle rollback request"""
        print(f"\n↩️  [NODE {self.node_id}] ROLLBACK for {transaction_id}")
        
        if transaction_id in self.transactions:
            transaction = self.transactions[transaction_id]
            
            # Release locks without making changes
            for acc_id in transaction.get("local_accounts", []):
                if acc_id in self.accounts:
                    self.accounts[acc_id].lock.release()
                    print(f"  🔓 Released lock for {acc_id}")
            
            transaction["status"] = "ROLLED_BACK"
            return {"status": "ROLLED_BACK", "message": "Transaction rolled back"}
        
        return {"status": "ERROR", "message": "Transaction not found"}
    
    def handle_crash(self) -> dict:
        """Simulate node crash"""
        print(f"\n🔥 [NODE {self.node_id}] SIMULATING CRASH!")
        self.active = False
        
        # Release all locks
        for account in self.accounts.values():
            try:
                account.lock.release()
            except:
                pass
        
        return {"status": "CRASHED", "message": "Node has crashed"}
    
    def handle_recover(self) -> dict:
        """Recover from crash"""
        print(f"\n✅ [NODE {self.node_id}] RECOVERING FROM CRASH")
        self.active = True
        
        # Clear any prepared transactions (in real system, would use logs)
        to_remove = []
        for txn_id, txn in self.transactions.items():
            if txn.get("status") == "PREPARED":
                to_remove.append(txn_id)
        
        for txn_id in to_remove:
            del self.transactions[txn_id]
        
        return {"status": "RECOVERED", "message": "Node recovered"}
    
    def handle_request(self, message: dict) -> dict:
        """Handle incoming request"""
        msg_type = message.get("type")
        
        if msg_type == "PREPARE":
            return self.handle_prepare(
                message["transaction_id"],
                message.get("accounts", []),
                message["from_account"],
                message["to_account"],
                message["amount"]
            )
        
        elif msg_type == "COMMIT":
            return self.handle_commit(message["transaction_id"])
        
        elif msg_type == "ROLLBACK":
            return self.handle_rollback(message["transaction_id"])
        
        elif msg_type == "CHECK_ACCOUNTS":
            accounts = message.get("accounts", [])
            node_accounts = [acc for acc in accounts if acc in self.accounts]
            return {"status": "OK", "accounts": node_accounts}
        
        elif msg_type == "STATUS":
            accounts_info = [
                {"id": acc.id, "balance": acc.balance}
                for acc in self.accounts.values()
            ]
            return {
                "status": "OK",
                "node_id": self.node_id,
                "active": self.active,
                "accounts": accounts_info,
                "pending_transactions": len([
                    t for t in self.transactions.values() 
                    if t.get("status") == "PREPARED"
                ])
            }
        
        elif msg_type == "CRASH":
            return self.handle_crash()
        
        elif msg_type == "RECOVER":
            return self.handle_recover()
        
        else:
            return {"status": "ERROR", "message": f"Unknown message type: {msg_type}"}
    
    def handle_connection(self, client_socket: socket.socket):
        """Handle incoming connection"""
        try:
            data = client_socket.recv(4096)
            if data:
                message = json.loads(data.decode())
                response = self.handle_request(message)
                client_socket.sendall(json.dumps(response).encode())
        except Exception as e:
            print(f"Error handling connection: {e}")
        finally:
            client_socket.close()
    
    def start_server(self):
        """Start the node server"""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.host, self.port))
        server.listen(10)
        
        print(f"\n🖥️  Node {self.node_id} server started on {self.host}:{self.port}")
        print("Waiting for coordinator requests...")
        
        while self.running:
            try:
                client, address = server.accept()
                threading.Thread(
                    target=self.handle_connection,
                    args=(client,),
                    daemon=True
                ).start()
            except Exception as e:
                if self.running:
                    print(f"Server error: {e}")
        
        server.close()
    
    def node_cli(self):
        """Command Line Interface for Node"""
        print("\n" + "="*60)
        print(f"🎮 NODE {self.node_id} COMMAND INTERFACE")
        print("="*60)
        print("Commands:")
        print("  crash    - Simulate node crash")
        print("  recover  - Recover node")
        print("  status   - Show node status")
        print("  quit     - Exit")
        print("="*60)
        
        while True:
            try:
                cmd = input(f"\n{self.node_id}> ").strip().lower()
                
                if cmd == "crash":
                    self.handle_crash()
                    print("💥 Node crashed! Try a transaction from coordinator...")
                
                elif cmd == "recover":
                    self.handle_recover()
                    print("🔄 Node recovered and ready for transactions")
                
                elif cmd == "status":
                    print(f"\n📊 Node {self.node_id} Status:")
                    print(f"  Active: {'🟢 ONLINE' if self.active else '🔴 OFFLINE'}")
                    print(f"  Accounts:")
                    for acc in self.accounts.values():
                        print(f"    {acc}")
                    pending = len([
                        t for t in self.transactions.values() 
                        if t.get("status") == "PREPARED"
                    ])
                    print(f"  Pending transactions: {pending}")
                
                elif cmd == "quit":
                    print("Shutting down node...")
                    self.running = False
                    break
                
                else:
                    print("❌ Unknown command. Try: crash, recover, status, quit")
            
            except KeyboardInterrupt:
                print("\nShutting down node...")
                self.running = False
                break
            except Exception as e:
                print(f"❌ Error: {e}")

# ========== MAIN FUNCTION ==========

def run_coordinator():
    """Run the coordinator"""
    print("\n" + "="*60)
    print("🏦 STARTING DISTRIBUTED TRANSACTION COORDINATOR")
    print("="*60)
    
    coordinator = Coordinator('localhost', 5000)
    
    # Start server in background thread
    server_thread = threading.Thread(target=coordinator.start_server, daemon=True)
    server_thread.start()
    
    # Give server time to start
    time.sleep(1)
    
    # Start CLI
    coordinator.coordinator_cli()

def run_node(node_id):
    """Run a participant node"""
    print("\n" + "="*60)
    print(f"🖥️  STARTING NODE {node_id}")
    print("="*60)
    
    node = ParticipantNode(node_id, coordinator_host='localhost', coordinator_port=5000)
    
    # Start server in background thread
    server_thread = threading.Thread(target=node.start_server, daemon=True)
    server_thread.start()
    
    # Give server time to start
    time.sleep(1)
    
    # Start CLI
    node.node_cli()

def main():
    """Main entry point"""
    print("="*60)
    print("🏦 FAULT-TOLERANT DISTRIBUTED TRANSACTION SYSTEM")
    print("ICS 2403: Distributed Computing and Applications")
    print("="*60)
    
    if len(sys.argv) < 2:
        print("\n❌ Usage:")
        print("  To run coordinator: python distributed_system.py coordinator")
        print("  To run node:       python distributed_system.py node <NODE_ID>")
        print("\nExamples:")
        print("  Terminal 1: python distributed_system.py coordinator")
        print("  Terminal 2: python distributed_system.py node NODE-1")
        print("  Terminal 3: python distributed_system.py node NODE-2")
        print("  Terminal 4: python distributed_system.py node NODE-3")
        return
    
    mode = sys.argv[1].lower()
    
    if mode == "coordinator":
        run_coordinator()
    elif mode == "node":
        if len(sys.argv) < 3:
            print("❌ Please specify node ID. Usage: python distributed_system.py node NODE-1")
            return
        node_id = sys.argv[2].upper()
        if node_id not in ["NODE-1", "NODE-2", "NODE-3"]:
            print("❌ Invalid node ID. Use NODE-1, NODE-2, or NODE-3")
            return
        run_node(node_id)
    else:
        print(f"❌ Invalid mode: {mode}. Use 'coordinator' or 'node'")

if __name__ == "__main__":
    main()