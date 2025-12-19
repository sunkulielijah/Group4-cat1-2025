import socket
import json
import threading
import time
import sys
import uuid
from datetime import datetime

# ========== DISTRIBUTED TRANSACTION SYSTEM ==========

class Account:
    """Bank account with locking for concurrency control"""
    def __init__(self, account_id, initial_balance):
        self.account_id = account_id
        self.balance = initial_balance
        self.lock = threading.Lock()
        self.transaction_history = []
    
    def __str__(self):
        return f"{self.account_id}: ${self.balance:.2f}"

class NodeServer:
    """A node in the distributed system"""
    def __init__(self, node_id, port_offset=0):
        self.node_id = node_id
        self.host = "localhost"
        self.port = 6000 + port_offset
        self.accounts = self._initialize_accounts()
        self.transactions = {}
        self.is_active = True
        self.server_socket = None
        self.running = True
        
        print(f"🖥️  Node {node_id} initialized on port {self.port}")
        print(f"   Accounts: {[str(acc) for acc in self.accounts.values()]}")
    
    def _initialize_accounts(self):
        """Initialize accounts for this node"""
        if self.node_id == "NODE-1":
            return {
                "ACC001": Account("ACC001", 1000.0),
                "ACC002": Account("ACC002", 2000.0)
            }
        elif self.node_id == "NODE-2":
            return {
                "ACC003": Account("ACC003", 1500.0),
                "ACC004": Account("ACC004", 3000.0)
            }
        else:  # NODE-3
            return {
                "ACC005": Account("ACC005", 500.0),
                "ACC006": Account("ACC006", 1000.0)
            }
    
    def handle_request(self, request_data):
        """Handle incoming requests from coordinator"""
        request = json.loads(request_data)
        response = {"status": "ERROR", "message": "Unknown request"}
        
        if request["action"] == "prepare":
            response = self.prepare_transaction(request)
        elif request["action"] == "commit":
            response = self.commit_transaction(request)
        elif request["action"] == "rollback":
            response = self.rollback_transaction(request)
        elif request["action"] == "status":
            response = self.get_status()
        elif request["action"] == "crash":
            response = self.simulate_crash()
        elif request["action"] == "recover":
            response = self.recover()
        
        return json.dumps(response)
    
    def prepare_transaction(self, request):
        """Phase 1 of 2PC: Prepare transaction"""
        if not self.is_active:
            return {"status": "ERROR", "message": "Node is down"}
        
        transaction_id = request["transaction_id"]
        from_account = request.get("from_account")
        to_account = request.get("to_account")
        amount = request.get("amount", 0)
        
        print(f"[{self.node_id}] Preparing transaction {transaction_id}")
        
        # Check if we have the accounts
        our_accounts = []
        if from_account in self.accounts:
            our_accounts.append(from_account)
        if to_account in self.accounts:
            our_accounts.append(to_account)
        
        if not our_accounts:
            return {"status": "READY", "message": "No accounts here"}
        
        # Try to acquire locks (concurrency control)
        locked_accounts = []
        for acc_id in our_accounts:
            account = self.accounts[acc_id]
            if account.lock.acquire(blocking=False):
                locked_accounts.append(acc_id)
                print(f"  🔒 Locked {acc_id}")
            else:
                # Release any locks we already acquired
                for locked in locked_accounts:
                    self.accounts[locked].lock.release()
                return {"status": "ABORT", "message": f"Failed to lock {acc_id}"}
        
        # Check if we have enough balance for debit
        if from_account in our_accounts:
            if self.accounts[from_account].balance < amount:
                for acc_id in locked_accounts:
                    self.accounts[acc_id].lock.release()
                return {"status": "ABORT", "message": "Insufficient funds"}
        
        # Store transaction state
        self.transactions[transaction_id] = {
            "from_account": from_account,
            "to_account": to_account,
            "amount": amount,
            "locked_accounts": locked_accounts,
            "status": "PREPARED"
        }
        
        return {"status": "READY", "message": "Prepared successfully"}
    
    def commit_transaction(self, request):
        """Phase 2 of 2PC: Commit transaction"""
        transaction_id = request["transaction_id"]
        
        if transaction_id not in self.transactions:
            return {"status": "ERROR", "message": "Transaction not found"}
        
        transaction = self.transactions[transaction_id]
        print(f"[{self.node_id}] Committing transaction {transaction_id}")
        
        # Execute the transfer
        if transaction["from_account"] in self.accounts:
            self.accounts[transaction["from_account"]].balance -= transaction["amount"]
            self.accounts[transaction["from_account"]].transaction_history.append(
                f"[-${transaction['amount']:.2f}] {transaction_id}"
            )
        
        if transaction["to_account"] in self.accounts:
            self.accounts[transaction["to_account"]].balance += transaction["amount"]
            self.accounts[transaction["to_account"]].transaction_history.append(
                f"[+${transaction['amount']:.2f}] {transaction_id}"
            )
        
        # Release locks
        for acc_id in transaction["locked_accounts"]:
            self.accounts[acc_id].lock.release()
            print(f"  🔓 Released {acc_id}")
        
        transaction["status"] = "COMMITTED"
        return {"status": "COMMITTED", "message": "Transaction completed"}
    
    def rollback_transaction(self, request):
        """Rollback a prepared transaction"""
        transaction_id = request["transaction_id"]
        
        if transaction_id in self.transactions:
            transaction = self.transactions[transaction_id]
            print(f"[{self.node_id}] Rolling back transaction {transaction_id}")
            
            # Release locks without making changes
            for acc_id in transaction.get("locked_accounts", []):
                if acc_id in self.accounts:
                    self.accounts[acc_id].lock.release()
            
            transaction["status"] = "ROLLED_BACK"
            return {"status": "ROLLED_BACK", "message": "Transaction rolled back"}
        
        return {"status": "ERROR", "message": "Transaction not found"}
    
    def get_status(self):
        """Return node status"""
        accounts_info = []
        for acc in self.accounts.values():
            accounts_info.append({
                "id": acc.account_id,
                "balance": acc.balance,
                "locked": acc.lock.locked()
            })
        
        return {
            "status": "OK",
            "node_id": self.node_id,
            "active": self.is_active,
            "accounts": accounts_info,
            "pending_transactions": len([t for t in self.transactions.values() 
                                       if t.get("status") == "PREPARED"])
        }
    
    def simulate_crash(self):
        """Simulate node failure"""
        print(f"\n💥 [{self.node_id}] SIMULATING CRASH!")
        self.is_active = False
        
        # Release all locks (simulating crash)
        for account in self.accounts.values():
            try:
                account.lock.release()
            except:
                pass
        
        return {"status": "CRASHED", "message": "Node crashed"}
    
    def recover(self):
        """Recover from crash"""
        print(f"\n✅ [{self.node_id}] RECOVERING")
        self.is_active = True
        
        # Clear prepared transactions (would use logs in real system)
        to_remove = []
        for txn_id, txn in self.transactions.items():
            if txn.get("status") == "PREPARED":
                to_remove.append(txn_id)
        
        for txn_id in to_remove:
            del self.transactions[txn_id]
        
        return {"status": "RECOVERED", "message": "Node recovered"}
    
    def start(self):
        """Start the node server"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        
        print(f"🖥️  Node {self.node_id} listening on {self.host}:{self.port}")
        
        while self.running:
            try:
                client_socket, address = self.server_socket.accept()
                data = client_socket.recv(4096).decode()
                if data:
                    response = self.handle_request(data)
                    client_socket.send(response.encode())
                client_socket.close()
            except KeyboardInterrupt:
                break
            except Exception as e:
                if self.running:
                    print(f"Node {self.node_id} error: {e}")
        
        self.server_socket.close()
    
    def node_cli(self):
        """Node command line interface"""
        print(f"\n📟 Node {self.node_id} CLI")
        print("Commands: crash | recover | status | quit")
        
        while True:
            try:
                cmd = input(f"\n{self.node_id}> ").strip().lower()
                
                if cmd == "crash":
                    self.simulate_crash()
                elif cmd == "recover":
                    self.recover()
                elif cmd == "status":
                    status = self.get_status()
                    print(f"\nStatus: {'🟢 ACTIVE' if self.is_active else '🔴 INACTIVE'}")
                    print("Accounts:")
                    for acc in self.accounts.values():
                        print(f"  {acc}")
                elif cmd == "quit":
                    print(f"Shutting down {self.node_id}...")
                    self.running = False
                    break
                else:
                    print("Unknown command. Try: crash, recover, status, quit")
            
            except KeyboardInterrupt:
                print(f"\nShutting down {self.node_id}...")
                self.running = False
                break

class Coordinator:
    """Coordinator for distributed transactions"""
    def __init__(self):
        self.host = "localhost"
        self.port = 5000
        self.nodes = {}  # node_id -> (host, port)
        self.transactions = {}
        self.server_socket = None
        self.running = True
    
    def send_to_node(self, node_id, message):
        """Send message to a node and get response"""
        if node_id not in self.nodes:
            return {"status": "ERROR", "message": f"Node {node_id} not found"}
        
        host, port = self.nodes[node_id]
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2)
                s.connect((host, port))
                s.send(json.dumps(message).encode())
                response = s.recv(4096).decode()
                return json.loads(response)
        except Exception as e:
            print(f"Failed to contact {node_id}: {e}")
            return {"status": "ERROR", "message": str(e)}
    
    def broadcast(self, message, exclude=None):
        """Send message to all nodes"""
        responses = {}
        for node_id in list(self.nodes.keys()):
            if exclude and node_id == exclude:
                continue
            responses[node_id] = self.send_to_node(node_id, message)
        return responses
    
    def register_node(self, node_id, host, port):
        """Register a new node"""
        self.nodes[node_id] = (host, port)
        print(f"✅ Node {node_id} registered at {host}:{port}")
    
    def execute_transaction(self, from_account, to_account, amount):
        """Execute a distributed transaction using 2-Phase Commit"""
        transaction_id = f"TXN-{uuid.uuid4().hex[:8]}"
        
        print(f"\n{'='*60}")
        print(f"🚀 Starting Transaction {transaction_id}")
        print(f"💸 Transfer: ${amount:.2f} from {from_account} to {to_account}")
        print(f"{'='*60}")
        
        # PHASE 1: PREPARE
        print("\n📋 PHASE 1: PREPARE (Voting)")
        prepare_results = {}
        
        # Send prepare to all nodes
        for node_id in self.nodes:
            prepare_msg = {
                "action": "prepare",
                "transaction_id": transaction_id,
                "from_account": from_account,
                "to_account": to_account,
                "amount": amount
            }
            
            result = self.send_to_node(node_id, prepare_msg)
            prepare_results[node_id] = result
            
            status = "✅ READY" if result.get("status") == "READY" else "❌ ABORT"
            print(f"  {node_id}: {status} - {result.get('message', '')}")
        
        # Check if all nodes are ready
        all_ready = all(r.get("status") in ["READY", "NO_ACCOUNTS"] for r in prepare_results.values())
        
        if not all_ready:
            print("\n⚠️  Transaction Aborted: Prepare failed")
            print("🔄 Rolling back...")
            
            # Send rollback to all nodes
            rollback_msg = {"action": "rollback", "transaction_id": transaction_id}
            self.broadcast(rollback_msg)
            
            self.transactions[transaction_id] = {"status": "ABORTED"}
            return {"status": "ABORTED", "transaction_id": transaction_id}
        
        # PHASE 2: COMMIT
        print("\n📋 PHASE 2: COMMIT (Execution)")
        commit_results = self.broadcast({
            "action": "commit",
            "transaction_id": transaction_id
        })
        
        # Check commit results
        successful = sum(1 for r in commit_results.values() if r.get("status") == "COMMITTED")
        
        if successful == len(commit_results):
            print(f"\n🎉 Transaction {transaction_id} SUCCESSFULLY COMMITTED!")
            status = "COMMITTED"
        else:
            print(f"\n⚠️  Partial Commit: {successful}/{len(commit_results)} nodes succeeded")
            status = "PARTIAL_COMMIT"
        
        # Store transaction record
        self.transactions[transaction_id] = {
            "from_account": from_account,
            "to_account": to_account,
            "amount": amount,
            "status": status,
            "timestamp": datetime.now().isoformat()
        }
        
        return {"status": status, "transaction_id": transaction_id}
    
    def simulate_concurrent_transfers(self, num_transfers=4):
        """Simulate multiple concurrent transfers (RANDOM)"""
        print(f"\n{'='*60}")
        print(f"🧪 RANDOM CONCURRENT TRANSFERS ({num_transfers} transactions)")
        print("="*60)
        
        import random
        accounts = ["ACC001", "ACC002", "ACC003", "ACC004", "ACC005", "ACC006"]
        
        # Create random transfer requests
        transfers = []
        for i in range(num_transfers):
            from_acc = random.choice(accounts)
            to_acc = random.choice([a for a in accounts if a != from_acc])
            amount = random.uniform(10, 200)
            transfers.append((from_acc, to_acc, amount))
        
        print(f"\n📋 Random Transactions:")
        for i, (frm, to, amt) in enumerate(transfers):
            print(f"  {i+1}. ${amt:.2f} from {frm} to {to}")
        
        input("\nPress Enter to start concurrent execution...")
        
        # Execute all transactions concurrently
        threads = []
        results = []
        results_lock = threading.Lock()
        
        def transfer_thread(from_acc, to_acc, amt, client_id):
            print(f"\n👤 {client_id} STARTING: ${amt:.2f} {from_acc}→{to_acc}")
            result = self.execute_transaction(from_acc, to_acc, amt)
            print(f"   {client_id} RESULT: {result['status']}")
            
            with results_lock:
                results.append(result)
        
        # Start all threads
        print(f"\n🚦 STARTING ALL {num_transfers} TRANSACTIONS SIMULTANEOUSLY...")
        for i, (from_acc, to_acc, amount) in enumerate(transfers):
            thread = threading.Thread(
                target=transfer_thread,
                args=(from_acc, to_acc, amount, f"Client-{i+1}"),
                daemon=True
            )
            threads.append(thread)
        
        # Start all threads at once
        for thread in threads:
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join(timeout=10)
        
        # Show final results
        successful = sum(1 for r in results if r.get("status") == "COMMITTED")
        print(f"\n{'='*60}")
        print("📊 FINAL RESULTS:")
        print(f"  Total transactions: {num_transfers}")
        print(f"  Successful: {successful}")
        print(f"  Failed/Aborted: {num_transfers - successful}")
        
        return results
    
    def execute_custom_concurrent_transfers(self):
        """LET USER INPUT THEIR OWN TRANSACTIONS TO RUN CONCURRENTLY"""
        print(f"\n{'='*60}")
        print("🧪 CUSTOM CONCURRENT TRANSFERS")
        print("="*60)
        
        # Get transactions from user
        transactions = []
        print("\nEnter transactions (leave 'from' empty to finish):")
        
        while True:
            from_acc = input(f"\nTransaction {len(transactions)+1} - From account: ").strip()
            if not from_acc:
                break
            
            to_acc = input("To account: ").strip()
            try:
                amount = float(input("Amount: $").strip())
            except:
                print("❌ Invalid amount, using $100")
                amount = 100.0
            
            transactions.append((from_acc, to_acc, amount))
        
        if not transactions:
            print("❌ No transactions entered")
            return []
        
        print(f"\n📋 Will execute {len(transactions)} transactions concurrently:")
        for i, (frm, to, amt) in enumerate(transactions):
            print(f"  {i+1}. ${amt:.2f} from {frm} to {to}")
        
        input("\nPress Enter to start concurrent execution...")
        
        # Execute all transactions concurrently
        threads = []
        results = []
        results_lock = threading.Lock()
        
        def transfer_thread(from_acc, to_acc, amt, client_id):
            print(f"\n👤 {client_id} STARTING: ${amt:.2f} {from_acc}→{to_acc}")
            result = self.execute_transaction(from_acc, to_acc, amt)
            print(f"   {client_id} RESULT: {result['status']}")
            
            with results_lock:
                results.append(result)
        
        # Start ALL threads at the same time
        print(f"\n🚦 STARTING ALL {len(transactions)} TRANSACTIONS SIMULTANEOUSLY...")
        for i, (from_acc, to_acc, amount) in enumerate(transactions):
            thread = threading.Thread(
                target=transfer_thread,
                args=(from_acc, to_acc, amount, f"Client-{i+1}"),
                daemon=True
            )
            threads.append(thread)
        
        # Start all threads at once
        for thread in threads:
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join(timeout=10)
        
        # Show final results
        successful = sum(1 for r in results if r.get("status") == "COMMITTED")
        print(f"\n{'='*60}")
        print("📊 FINAL RESULTS:")
        print(f"  Total transactions: {len(transactions)}")
        print(f"  Successful: {successful}")
        print(f"  Failed/Aborted: {len(transactions) - successful}")
        
        if successful < len(transactions):
            print("\n⚠️  Some transactions failed due to concurrency conflicts!")
            print("   (Accounts were locked by other transactions)")
        
        return results
    
    def execute_conflict_test(self):
        """Pre-defined test that forces concurrency conflicts"""
        print(f"\n{'='*60}")
        print("🔥 FORCED CONCURRENCY CONFLICT TEST")
        print("="*60)
        print("All clients will try to use ACC001 at the same time!")
        
        # All clients try to use ACC001
        test_transactions = [
            ("ACC001", "ACC002", 100.0),
            ("ACC001", "ACC003", 200.0),
            ("ACC001", "ACC004", 150.0),
            ("ACC002", "ACC001", 50.0),
        ]
        
        print("\n📋 Test Transactions:")
        for i, (frm, to, amt) in enumerate(test_transactions):
            print(f"  Client-{i+1}: ${amt:.2f} from {frm} to {to}")
        
        input("\nPress Enter to start the conflict test...")
        
        # Execute concurrently
        threads = []
        results = []
        results_lock = threading.Lock()
        
        def test_thread(from_acc, to_acc, amt, client_id):
            print(f"\n⚡ {client_id} STARTING...")
            result = self.execute_transaction(from_acc, to_acc, amt)
            print(f"   {client_id} RESULT: {result['status']}")
            
            with results_lock:
                results.append(result)
        
        # Start all threads
        for i, (from_acc, to_acc, amount) in enumerate(test_transactions):
            thread = threading.Thread(
                target=test_thread,
                args=(from_acc, to_acc, amount, f"Client-{i+1}"),
                daemon=True
            )
            threads.append(thread)
        
        print(f"\n🚦 STARTING ALL 4 CLIENTS SIMULTANEOUSLY...")
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join(timeout=5)
        
        successful = sum(1 for r in results if r.get("status") == "COMMITTED")
        print(f"\n📊 CONFLICT TEST RESULTS:")
        print(f"  Successful: {successful}/4")
        print(f"  (Due to lock contention on ACC001)")
        
        return results
    
    def get_system_status(self):
        """Get status of all nodes"""
        status = {}
        for node_id in self.nodes:
            response = self.send_to_node(node_id, {"action": "status"})
            status[node_id] = response
        return status
    
    def handle_client(self, client_socket):
        """Handle incoming connections (node registrations)"""
        try:
            data = client_socket.recv(4096).decode()
            if data:
                message = json.loads(data)
                
                if message.get("action") == "register":
                    node_id = message["node_id"]
                    host = message["host"]
                    port = message["port"]
                    
                    self.register_node(node_id, host, port)
                    client_socket.send(json.dumps({
                        "status": "REGISTERED",
                        "node_id": node_id
                    }).encode())
                
                elif message.get("action") == "transaction":
                    from_acc = message.get("from_account")
                    to_acc = message.get("to_account")
                    amount = message.get("amount")
                    
                    result = self.execute_transaction(from_acc, to_acc, amount)
                    client_socket.send(json.dumps(result).encode())
        
        except Exception as e:
            print(f"Client handling error: {e}")
        finally:
            client_socket.close()
    
    def start(self):
        """Start coordinator server"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        
        print(f"🎯 Coordinator started on {self.host}:{self.port}")
        print("Waiting for nodes to register...")
        
        # Start server thread
        def server_loop():
            while self.running:
                try:
                    client, address = self.server_socket.accept()
                    threading.Thread(
                        target=self.handle_client,
                        args=(client,),
                        daemon=True
                    ).start()
                except:
                    break
        
        server_thread = threading.Thread(target=server_loop, daemon=True)
        server_thread.start()
    
    def coordinator_cli(self):
        """Coordinator command line interface"""
        print("\n" + "="*60)
        print("🎮 COORDINATOR COMMAND INTERFACE")
        print("="*60)
        print("Commands:")
        print("  status      - Check system status")
        print("  transfer    - Execute a single transfer")
        print("  custom      - Input YOUR OWN concurrent transfers")
        print("  conflict    - Run forced concurrency test")
        print("  random      - Run random concurrent transfers")
        print("  quit        - Exit")
        print("="*60)
        
        while True:
            try:
                cmd = input("\ncoordinator> ").strip().lower()
                
                if cmd == "status":
                    print("\n📊 SYSTEM STATUS:")
                    status = self.get_system_status()
                    for node_id, info in status.items():
                        if info.get("status") == "OK":
                            active = "🟢 ONLINE" if info.get("active") else "🔴 OFFLINE"
                            print(f"  {node_id}: {active}")
                            for acc in info.get("accounts", []):
                                locked = "🔒" if acc.get("locked") else "  "
                                print(f"    {locked} {acc['id']}: ${acc['balance']:.2f}")
                
                elif cmd == "transfer":
                    try:
                        from_acc = input("From account: ").strip()
                        to_acc = input("To account: ").strip()
                        amount = float(input("Amount: $").strip())
                        
                        result = self.execute_transaction(from_acc, to_acc, amount)
                        print(f"\nResult: {result['status']}")
                        if result.get("transaction_id"):
                            print(f"Transaction ID: {result['transaction_id']}")
                    except ValueError:
                        print("❌ Invalid amount")
                    except Exception as e:
                        print(f"❌ Error: {e}")
                
                elif cmd == "custom":
                    # NEW: Let user input their own concurrent transfers
                    self.execute_custom_concurrent_transfers()
                
                elif cmd == "conflict":
                    # Pre-defined conflict test
                    self.execute_conflict_test()
                
                elif cmd == "random":
                    try:
                        num = input("Number of random transfers (default 4): ").strip()
                        num_transfers = int(num) if num else 4
                        self.simulate_concurrent_transfers(num_transfers)
                    except ValueError:
                        print("❌ Invalid number. Using default of 4.")
                        self.simulate_concurrent_transfers(4)
                
                elif cmd == "quit":
                    print("Shutting down coordinator...")
                    self.running = False
                    break
                
                else:
                    print("Unknown command. Try: status, transfer, custom, conflict, random, quit")
            
            except KeyboardInterrupt:
                print("\nShutting down coordinator...")
                self.running = False
                break
            except Exception as e:
                print(f"Error: {e}")

# ========== MAIN EXECUTION ==========

def run_coordinator():
    """Run the coordinator"""
    print("\n" + "="*60)
    print("🏦 DISTRIBUTED TRANSACTION COORDINATOR")
    print("="*60)
    
    coordinator = Coordinator()
    coordinator.start()
    time.sleep(1)  # Give server time to start
    coordinator.coordinator_cli()

def run_node(node_id):
    """Run a node"""
    print("\n" + "="*60)
    print(f"🖥️  STARTING NODE: {node_id}")
    print("="*60)
    
    # Map node IDs to port offsets
    port_offsets = {"NODE-1": 1, "NODE-2": 2, "NODE-3": 3}
    
    if node_id not in port_offsets:
        print(f"❌ Invalid node ID. Use: NODE-1, NODE-2, or NODE-3")
        return
    
    # Create and start node
    node = NodeServer(node_id, port_offsets[node_id])
    
    # Register with coordinator
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect(("localhost", 5000))
            s.send(json.dumps({
                "action": "register",
                "node_id": node_id,
                "host": "localhost",
                "port": 6000 + port_offsets[node_id]
            }).encode())
            response = s.recv(4096).decode()
            print(f"Registration: {json.loads(response).get('status')}")
    except:
        print("⚠️  Could not register with coordinator. Make sure coordinator is running first.")
    
    # Start node server in background thread
    server_thread = threading.Thread(target=node.start, daemon=True)
    server_thread.start()
    
    # Start CLI
    node.node_cli()

def main():
    """Main entry point"""
    print("="*60)
    print("🏦 FAULT-TOLERANT DISTRIBUTED TRANSACTION SYSTEM")
    print("ICS 2403: Distributed Computing - CAT 1")
    print("="*60)
    
    if len(sys.argv) < 2:
        print("\nUsage:")
        print("  To run coordinator: python script.py coordinator")
        print("  To run a node:     python script.py node <NODE-ID>")
        print("\nExamples:")
        print("  Terminal 1: python script.py coordinator")
        print("  Terminal 2: python script.py node NODE-1")
        print("  Terminal 3: python script.py node NODE-2")
        print("  Terminal 4: python script.py node NODE-3")
        return
    
    mode = sys.argv[1].lower()
    
    if mode == "coordinator":
        run_coordinator()
    elif mode == "node":
        if len(sys.argv) < 3:
            print("❌ Please specify node ID: NODE-1, NODE-2, or NODE-3")
            return
        node_id = sys.argv[2].upper()
        if node_id not in ["NODE-1", "NODE-2", "NODE-3"]:
            print("❌ Invalid node ID. Use: NODE-1, NODE-2, or NODE-3")
            return
        run_node(node_id)
    else:
        print(f"❌ Invalid mode: {mode}. Use 'coordinator' or 'node'")

if __name__ == "__main__":
    main()