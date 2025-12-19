import socket
import json
import threading
import time
import sys
import uuid

# ========== DISTRIBUTED TRANSACTION SYSTEM ==========

class Account:
    def __init__(self, account_id, initial_balance):
        self.account_id = account_id
        self.balance = initial_balance
        self.lock = threading.Lock()
    
    def __str__(self):
        return f"{self.account_id}: ${self.balance:.2f}"

class NodeServer:
    def __init__(self, node_id, port_offset=0):
        self.node_id = node_id
        self.host = "localhost"
        self.port = 6000 + port_offset
        self.accounts = self._initialize_accounts()
        self.transactions = {}
        self.is_active = True
        self.running = True
        
        self._print(f"🖥️  Node {node_id} on port {self.port}")
        for acc in self.accounts.values():
            self._print(f"   {acc}")
    
    def _print(self, message):
        """Print with node identifier"""
        print(f"[{self.node_id}] {message}")
    
    def _initialize_accounts(self):
        if self.node_id == "NODE-1":
            return {"ACC001": Account("ACC001", 1000.0), "ACC002": Account("ACC002", 2000.0)}
        elif self.node_id == "NODE-2":
            return {"ACC003": Account("ACC003", 1500.0), "ACC004": Account("ACC004", 3000.0)}
        else:
            return {"ACC005": Account("ACC005", 500.0), "ACC006": Account("ACC006", 1000.0)}
    
    def handle_request(self, request_data):
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
        if not self.is_active:
            self._print(f"❌ Cannot prepare: Node is down")
            return {"status": "ERROR", "message": "Node is down"}
        
        transaction_id = request["transaction_id"]
        from_account = request.get("from_account")
        to_account = request.get("to_account")
        amount = request.get("amount", 0)
        
        self._print(f"📋 PREPARE request for transaction {transaction_id}")
        self._print(f"   From: {from_account}, To: {to_account}, Amount: ${amount:.2f}")
        
        # Check which accounts are on this node
        our_accounts = []
        if from_account in self.accounts:
            our_accounts.append(from_account)
            self._print(f"   ✓ Account {from_account} is on this node")
        if to_account in self.accounts:
            our_accounts.append(to_account)
            self._print(f"   ✓ Account {to_account} is on this node")
        
        if not our_accounts:
            self._print(f"   ℹ️  No accounts from this transaction are on this node")
            return {"status": "READY", "message": "No accounts here"}
        
        # Try to acquire locks
        locked_accounts = []
        for acc_id in our_accounts:
            account = self.accounts[acc_id]
            if account.lock.acquire(blocking=False):
                locked_accounts.append(acc_id)
                self._print(f"   🔒 Locked account {acc_id}")
            else:
                # Release any locks we already acquired
                self._print(f"   ❌ Failed to lock account {acc_id} (already locked)")
                for locked in locked_accounts:
                    self.accounts[locked].lock.release()
                    self._print(f"   🔓 Released lock on {locked}")
                return {"status": "ABORT", "message": f"Failed to lock {acc_id}"}
        
        # Check balance
        if from_account in our_accounts:
            current_balance = self.accounts[from_account].balance
            if current_balance < amount:
                self._print(f"   ❌ Insufficient funds in {from_account}")
                self._print(f"      Current: ${current_balance:.2f}, Required: ${amount:.2f}")
                for acc_id in locked_accounts:
                    self.accounts[acc_id].lock.release()
                    self._print(f"   🔓 Released lock on {acc_id}")
                return {"status": "ABORT", "message": "Insufficient funds"}
            else:
                self._print(f"   ✓ Sufficient funds in {from_account}")
                self._print(f"      Current: ${current_balance:.2f}, After: ${current_balance - amount:.2f}")
        
        # Store transaction state
        self.transactions[transaction_id] = {
            "from_account": from_account,
            "to_account": to_account,
            "amount": amount,
            "locked_accounts": locked_accounts,
            "status": "PREPARED"
        }
        
        self._print(f"   ✅ PREPARE successful for transaction {transaction_id}")
        return {"status": "READY", "message": "Prepared successfully"}
    
    def commit_transaction(self, request):
        transaction_id = request["transaction_id"]
        
        self._print(f"💾 COMMIT request for transaction {transaction_id}")
        
        if transaction_id not in self.transactions:
            self._print(f"   ℹ️  Transaction not found (no accounts involved)")
            return {"status": "COMMITTED", "message": "No accounts involved"}
        
        transaction = self.transactions[transaction_id]
        
        # Execute the transfer
        if transaction["from_account"] in self.accounts:
            old_balance = self.accounts[transaction["from_account"]].balance
            self.accounts[transaction["from_account"]].balance -= transaction["amount"]
            new_balance = self.accounts[transaction["from_account"]].balance
            self._print(f"   ➖ Debited {transaction['from_account']}")
            self._print(f"      From: ${old_balance:.2f} → To: ${new_balance:.2f}")
        
        if transaction["to_account"] in self.accounts:
            old_balance = self.accounts[transaction["to_account"]].balance
            self.accounts[transaction["to_account"]].balance += transaction["amount"]
            new_balance = self.accounts[transaction["to_account"]].balance
            self._print(f"   ➕ Credited {transaction['to_account']}")
            self._print(f"      From: ${old_balance:.2f} → To: ${new_balance:.2f}")
        
        # Release locks
        for acc_id in transaction["locked_accounts"]:
            self.accounts[acc_id].lock.release()
            self._print(f"   🔓 Released lock on {acc_id}")
        
        transaction["status"] = "COMMITTED"
        
        self._print(f"   ✅ COMMIT successful for transaction {transaction_id}")
        return {"status": "COMMITTED", "message": "Transaction completed"}
    
    def rollback_transaction(self, request):
        transaction_id = request["transaction_id"]
        
        self._print(f"↩️  ROLLBACK request for transaction {transaction_id}")
        
        if transaction_id in self.transactions:
            transaction = self.transactions[transaction_id]
            
            # Release locks without making changes
            for acc_id in transaction.get("locked_accounts", []):
                if acc_id in self.accounts:
                    self.accounts[acc_id].lock.release()
                    self._print(f"   🔓 Released lock on {acc_id}")
            
            transaction["status"] = "ROLLED_BACK"
            self._print(f"   ✅ ROLLBACK completed for transaction {transaction_id}")
            return {"status": "ROLLED_BACK", "message": "Transaction rolled back"}
        
        self._print(f"   ℹ️  Transaction not found (already rolled back?)")
        return {"status": "ROLLED_BACK", "message": "Transaction not found"}
    
    def get_status(self):
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
            "accounts": accounts_info
        }
    
    def simulate_crash(self):
        self.is_active = False
        for account in self.accounts.values():
            try:
                account.lock.release()
            except:
                pass
        self._print("💥💥💥 NODE CRASHED 💥💥💥")
        return {"status": "CRASHED", "message": "Node crashed"}
    
    def recover(self):
        self.is_active = True
        to_remove = []
        for txn_id, txn in self.transactions.items():
            if txn.get("status") == "PREPARED":
                to_remove.append(txn_id)
        for txn_id in to_remove:
            del self.transactions[txn_id]
        self._print("✅✅✅ NODE RECOVERED ✅✅✅")
        return {"status": "RECOVERED", "message": "Node recovered"}
    
    def start(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.host, self.port))
        server.listen(5)
        
        self._print(f"🖥️  Node {self.node_id} listening on {self.host}:{self.port}")
        
        while self.running:
            try:
                client_socket, address = server.accept()
                data = client_socket.recv(4096).decode()
                if data:
                    response = self.handle_request(data)
                    client_socket.send(response.encode())
                client_socket.close()
            except KeyboardInterrupt:
                break
            except:
                continue
        
        server.close()
    
    def node_cli(self):
        self._print(f"\n📟 Node {self.node_id} CLI")
        self._print("Commands: crash | recover | status | quit")
        
        while True:
            try:
                cmd = input(f"\n{self.node_id}> ").strip().lower()
                
                if cmd == "crash":
                    self.simulate_crash()
                elif cmd == "recover":
                    self.recover()
                elif cmd == "status":
                    status = self.get_status()
                    self._print(f"\nStatus: {'🟢 ACTIVE' if self.is_active else '🔴 INACTIVE'}")
                    for acc in self.accounts.values():
                        lock_status = " (LOCKED)" if acc.lock.locked() else ""
                        self._print(f"  {acc}{lock_status}")
                elif cmd == "quit":
                    self.running = False
                    break
                else:
                    self._print("Unknown command. Try: crash, recover, status, quit")
            
            except KeyboardInterrupt:
                self.running = False
                break

class Coordinator:
    def __init__(self):
        self.host = "localhost"
        self.port = 5000
        self.nodes = {}
        self.running = True
    
    def send_to_node(self, node_id, message):
        if node_id not in self.nodes:
            return {"status": "ERROR", "message": f"Node {node_id} not found"}
        
        host, port = self.nodes[node_id]
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(3)
                s.connect((host, port))
                s.send(json.dumps(message).encode())
                response = s.recv(4096).decode()
                return json.loads(response)
        except:
            return {"status": "ERROR", "message": f"Failed to reach {node_id}"}
    
    def broadcast(self, message, exclude=None):
        responses = {}
        for node_id in list(self.nodes.keys()):
            if exclude and node_id == exclude:
                continue
            responses[node_id] = self.send_to_node(node_id, message)
        return responses
    
    def register_node(self, node_id, host, port):
        self.nodes[node_id] = (host, port)
        print(f"✅ Node {node_id} registered at {host}:{port}")
    
    def execute_transaction(self, from_account, to_account, amount, transaction_name="Transaction"):
        transaction_id = f"TXN-{uuid.uuid4().hex[:8]}"
        
        print(f"\n{'='*60}")
        print(f"🚀 {transaction_name}: {transaction_id}")
        print(f"💸 ${amount:.2f} from {from_account} to {to_account}")
        
        # PHASE 1: PREPARE
        print(f"\n📋 PREPARE Phase for {transaction_name}:")
        prepare_results = {}
        
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
            print(f"  {node_id}: {status}")
        
        # Check if all nodes are ready
        all_ready = all(r.get("status") in ["READY", "NO_ACCOUNTS"] for r in prepare_results.values())
        
        if not all_ready:
            print(f"\n⚠️  {transaction_name} Aborted")
            rollback_msg = {"action": "rollback", "transaction_id": transaction_id}
            self.broadcast(rollback_msg)
            return {"status": "ABORTED", "transaction_id": transaction_id}
        
        # PHASE 2: COMMIT
        print(f"\n📋 COMMIT Phase for {transaction_name}:")
        commit_results = self.broadcast({
            "action": "commit",
            "transaction_id": transaction_id
        })
        
        successful = sum(1 for r in commit_results.values() if r.get("status") == "COMMITTED")
        
        if successful == len(commit_results):
            print(f"\n✅ {transaction_name} COMMITTED!")
            status = "COMMITTED"
        else:
            print(f"\n⚠️  Partial Commit for {transaction_name}: {successful}/{len(commit_results)} nodes")
            status = "PARTIAL_COMMIT"
        
        return {"status": status, "transaction_id": transaction_id}
    
    def execute_custom_concurrent_transfers(self):
        """Collect multiple transactions and execute them concurrently"""
        transactions = []
        
        print(f"\n{'='*60}")
        print("🧪 CUSTOM CONCURRENT TRANSFERS")
        print("="*60)
        print("Enter your transactions one by one.")
        print("When you're done, press Enter on an empty 'From account'.")
        print("="*60)
        
        transaction_num = 1
        
        while True:
            print(f"\n{'='*40}")
            print(f"TRANSACTION {transaction_num}")
            print('='*40)
            
            # Get From account
            print(f"Transaction {transaction_num} - From account: ", end="")
            from_acc = input().strip()
            
            # If user presses Enter without typing anything, we're done
            if not from_acc:
                break
            
            # Get To account
            print(f"Transaction {transaction_num} - To account: ", end="")
            to_acc = input().strip()
            
            # Get Amount
            print(f"Transaction {transaction_num} - Amount: $", end="")
            amount_str = input().strip().replace('$', '')
            
            try:
                amount = float(amount_str)
                
                # Add to transactions list
                transactions.append({
                    "name": f"Transaction {transaction_num}",
                    "from": from_acc,
                    "to": to_acc,
                    "amount": amount
                })
                
                print(f"\n✅ Added Transaction {transaction_num}:")
                print(f"   From: {from_acc}")
                print(f"   To: {to_acc}")
                print(f"   Amount: ${amount:.2f}")
                
                transaction_num += 1
                
            except ValueError:
                print("❌ Invalid amount. Please enter a valid number.")
        
        # Check if we have any transactions
        if not transactions:
            print("\n❌ No transactions entered. Returning to main menu.")
            return []
        
        # Show all transactions that will be executed
        print(f"\n{'='*60}")
        print("📋 ALL TRANSACTIONS TO EXECUTE")
        print("="*60)
        
        for txn in transactions:
            print(f"{txn['name']} - From account: {txn['from']}")
            print(f"{txn['name']} - To account: {txn['to']}")
            print(f"{txn['name']} - Amount: ${txn['amount']:.2f}")
            print()
        
        confirm = input(f"Execute {len(transactions)} transactions concurrently? (y/n): ").strip().lower()
        if confirm != 'y':
            print("❌ Execution cancelled.")
            return []
        
        print(f"\n🚀 Executing {len(transactions)} transactions SIMULTANEOUSLY...")
        
        # Execute all transactions concurrently
        threads = []
        results = []
        results_lock = threading.Lock()
        
        def execute_single_transaction(txn_data):
            """Function to execute a single transaction in a thread"""
            try:
                print(f"\n⚡ {txn_data['name']} STARTING...")
                result = self.execute_transaction(
                    txn_data['from'],
                    txn_data['to'],
                    txn_data['amount'],
                    txn_data['name']
                )
                
                with results_lock:
                    results.append({
                        "name": txn_data['name'],
                        "status": result['status'],
                        "from": txn_data['from'],
                        "to": txn_data['to'],
                        "amount": txn_data['amount']
                    })
                
                status_icon = "✅" if result['status'] == "COMMITTED" else "❌"
                print(f"{status_icon} {txn_data['name']} COMPLETED: {result['status']}")
                
            except Exception as e:
                print(f"❌ ERROR in {txn_data['name']}: {e}")
        
        print(f"\n{'='*60}")
        print("🚦 STARTING ALL TRANSACTIONS SIMULTANEOUSLY!")
        print("="*60)
        
        # Create and start threads for all transactions
        for txn in transactions:
            thread = threading.Thread(
                target=execute_single_transaction,
                args=(txn,),
                daemon=True
            )
            threads.append(thread)
        
        # Start ALL threads at the same time
        start_time = time.time()
        for thread in threads:
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join(timeout=10)
        
        execution_time = time.time() - start_time
        
        # Show final results
        print(f"\n{'='*60}")
        print("📊 CONCURRENT EXECUTION RESULTS")
        print("="*60)
        print(f"Total transactions: {len(transactions)}")
        print(f"Execution time: {execution_time:.2f} seconds")
        
        committed = sum(1 for r in results if r.get("status") == "COMMITTED")
        aborted = sum(1 for r in results if r.get("status") == "ABORTED")
        partial = sum(1 for r in results if r.get("status") == "PARTIAL_COMMIT")
        
        print(f"\n✅ Committed: {committed}")
        print(f"❌ Aborted: {aborted}")
        print(f"⚠️  Partial: {len(results) - committed - aborted}")
        
        # Show detailed results
        if results:
            print(f"\n📋 Detailed Results:")
            for result in results:
                status_icon = "✅" if result['status'] == "COMMITTED" else "❌"
                print(f"{status_icon} {result['name']}: {result['status']}")
                print(f"   From: {result['from']}")
                print(f"   To: {result['to']}")
                print(f"   Amount: ${result['amount']:.2f}")
        
        return results
    
    def execute_conflict_test(self):
        """Run a predefined conflict test"""
        print(f"\n{'='*60}")
        print("🔥 FORCED CONCURRENCY CONFLICT TEST")
        print("="*60)
        print("All transactions will try to use ACC001 at the same time!")
        
        # Predefined conflict transactions
        conflict_transactions = [
            {"name": "Conflict Test 1", "from": "ACC001", "to": "ACC002", "amount": 100.0},
            {"name": "Conflict Test 2", "from": "ACC001", "to": "ACC003", "amount": 200.0},
            {"name": "Conflict Test 3", "from": "ACC001", "to": "ACC004", "amount": 150.0},
            {"name": "Conflict Test 4", "from": "ACC002", "to": "ACC001", "amount": 50.0},
        ]
        
        print(f"\n📋 Will execute 4 conflicting transactions:")
        for txn in conflict_transactions:
            print(f"{txn['name']} - From account: {txn['from']}")
            print(f"{txn['name']} - To account: {txn['to']}")
            print(f"{txn['name']} - Amount: ${txn['amount']:.2f}")
            print()
        
        input("Press Enter to start the conflict test...")
        
        # Execute all transactions concurrently
        threads = []
        results = []
        results_lock = threading.Lock()
        
        def execute_single_transaction(txn_data):
            try:
                print(f"\n⚡ {txn_data['name']} STARTING...")
                result = self.execute_transaction(
                    txn_data['from'],
                    txn_data['to'],
                    txn_data['amount'],
                    txn_data['name']
                )
                
                with results_lock:
                    results.append({
                        "name": txn_data['name'],
                        "status": result['status'],
                        "from": txn_data['from'],
                        "to": txn_data['to'],
                        "amount": txn_data['amount']
                    })
                
                status_icon = "✅" if result['status'] == "COMMITTED" else "❌"
                print(f"{status_icon} {txn_data['name']} COMPLETED: {result['status']}")
                
            except Exception as e:
                print(f"❌ ERROR in {txn_data['name']}: {e}")
        
        print(f"\n{'='*60}")
        print("🚦 STARTING ALL 4 CONFLICTING TRANSACTIONS!")
        print("="*60)
        
        # Create and start threads for all transactions
        for txn in conflict_transactions:
            thread = threading.Thread(
                target=execute_single_transaction,
                args=(txn,),
                daemon=True
            )
            threads.append(thread)
        
        # Start ALL threads at the same time
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join(timeout=5)
        
        committed = sum(1 for r in results if r.get("status") == "COMMITTED")
        print(f"\n📊 CONFLICT TEST RESULTS:")
        print(f"  Successful: {committed}/4")
        print(f"  (Due to lock contention on ACC001)")
        
        return results
    
    def get_system_status(self):
        status = {}
        for node_id in self.nodes:
            response = self.send_to_node(node_id, {"action": "status"})
            status[node_id] = response
        return status
    
    def handle_client(self, client_socket):
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
        except:
            pass
        finally:
            client_socket.close()
    
    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        
        print(f"🎯 Coordinator started on {self.host}:{self.port}")
        print("Waiting for nodes to register...")
        
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
        print("\n" + "="*60)
        print("🎮 COORDINATOR COMMAND INTERFACE")
        print("="*60)
        print("Commands:")
        print("  status    - Check system status")
        print("  transfer  - Execute a single transfer")
        print("  custom    - Input MULTIPLE transactions and execute them CONCURRENTLY")
        print("  conflict  - Run forced concurrency test")
        print("  quit      - Exit")
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
                    print("\n🔽 SINGLE TRANSACTION")
                    print("Transaction - From account: ", end="")
                    from_acc = input().strip()
                    print("Transaction - To account: ", end="")
                    to_acc = input().strip()
                    print("Transaction - Amount: $", end="")
                    try:
                        amt = float(input().strip().replace('$', ''))
                        result = self.execute_transaction(from_acc, to_acc, amt)
                        print(f"\nResult: {result['status']}")
                    except ValueError:
                        print("❌ Invalid amount")
                
                elif cmd == "custom":
                    self.execute_custom_concurrent_transfers()
                
                elif cmd == "conflict":
                    self.execute_conflict_test()
                
                elif cmd == "quit":
                    self.running = False
                    break
                
                else:
                    print("❌ Unknown command. Try: status, transfer, custom, conflict, quit")
            
            except KeyboardInterrupt:
                self.running = False
                break
            except Exception as e:
                print(f"Error: {e}")

def run_coordinator():
    print("\n" + "="*60)
    print("🏦 DISTRIBUTED TRANSACTION COORDINATOR")
    print("="*60)
    
    coordinator = Coordinator()
    coordinator.start()
    time.sleep(1)
    coordinator.coordinator_cli()

def run_node(node_id):
    print("\n" + "="*60)
    print(f"🖥️  STARTING NODE: {node_id}")
    print("="*60)
    
    port_offsets = {"NODE-1": 1, "NODE-2": 2, "NODE-3": 3}
    
    if node_id not in port_offsets:
        print(f"❌ Invalid node ID. Use: NODE-1, NODE-2, or NODE-3")
        return
    
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
            s.recv(4096).decode()
    except:
        print("⚠️  Make sure coordinator is running first!")
    
    server_thread = threading.Thread(target=node.start, daemon=True)
    server_thread.start()
    
    node.node_cli()

def main():
    print("="*60)
    print("🏦 FAULT-TOLERANT DISTRIBUTED TRANSACTION SYSTEM")
    print("ICS 2403: Distributed Computing - CAT 1")
    print("="*60)
    
    if len(sys.argv) < 2:
        print("\nUsage:")
        print("  Coordinator: python distributed_system.py coordinator")
        print("  Node 1:      python distributed_system.py node NODE-1")
        print("  Node 2:      python distributed_system.py node NODE-2")
        print("  Node 3:      python distributed_system.py node NODE-3")
        return
    
    mode = sys.argv[1].lower()
    
    if mode == "coordinator":
        run_coordinator()
    elif mode == "node":
        if len(sys.argv) < 3:
            print("❌ Specify node ID: NODE-1, NODE-2, or NODE-3")
            return
        node_id = sys.argv[2].upper()
        if node_id not in ["NODE-1", "NODE-2", "NODE-3"]:
            print("❌ Invalid node ID")
            return
        run_node(node_id)
    else:
        print(f"❌ Invalid mode: {mode}")

if __name__ == "__main__":
    main()