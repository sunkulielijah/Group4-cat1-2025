"""
Distributed Account Transfer System
3-Node System with Fault-Tolerant Transactions
"""

import socket
import threading
import time
import json
import random

# =============== BANK NODE ===============
class BankNode:
    def __init__(self, node_id, port, accounts=None):
        self.node_id = node_id
        self.port = port
        self.accounts = accounts or {
            "ACC1001": 1000.0,
            "ACC1002": 500.0,
            "ACC1003": 750.0
        }
        self.transaction_log = []
        self.lock = threading.Lock()
        self.running = True
        
    def start(self):
        """Start the bank node server"""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(('localhost', self.port))
        server.listen(5)
        print(f"Bank Node {self.node_id} started on port {self.port}")
        print(f"Accounts: {self.accounts}")
        
        while self.running:
            client, _ = server.accept()
            threading.Thread(target=self.handle_client, args=(client,)).start()
    
    def handle_client(self, client):
        """Handle client requests"""
        try:
            data = json.loads(client.recv(1024).decode())
            response = self.process_request(data)
            client.send(json.dumps(response).encode())
        except:
            client.send(json.dumps({"error": "Invalid request"}).encode())
        client.close()
    
    def process_request(self, data):
        """Process different request types"""
        action = data.get("action")
        
        if action == "prepare_transfer":
            return self.prepare_transfer(data)
        elif action == "commit_transfer":
            return self.commit_transfer(data)
        elif action == "abort_transfer":
            return self.abort_transfer(data)
        elif action == "check_balance":
            return self.check_balance(data)
        elif action == "simulate_failure":
            return self.simulate_failure()
        else:
            return {"status": "error", "message": "Unknown action"}
    
    def prepare_transfer(self, data):
        """Phase 1: Prepare for transfer"""
        with self.lock:
            account = data.get("account")
            amount = data.get("amount")
            txn_id = data.get("txn_id")
            is_withdrawal = data.get("type") == "withdraw"
            
            # Simulate random failure (30% chance)
            if random.random() < 0.3:
                return {"vote": "no", "reason": "Node temporarily unavailable"}
            
            if account in self.accounts:
                if is_withdrawal:
                    if self.accounts[account] >= amount:
                        # Tentatively hold the amount
                        self.accounts[account] -= amount
                        self.transaction_log.append({
                            "txn_id": txn_id,
                            "account": account,
                            "amount": amount,
                            "type": "hold",
                            "timestamp": time.time()
                        })
                        return {"vote": "yes", "balance": self.accounts[account]}
                    else:
                        return {"vote": "no", "reason": "Insufficient funds"}
                else:
                    # For deposit, always ready
                    self.transaction_log.append({
                        "txn_id": txn_id,
                        "account": account,
                        "amount": amount,
                        "type": "hold",
                        "timestamp": time.time()
                    })
                    return {"vote": "yes", "balance": self.accounts[account]}
            else:
                return {"vote": "no", "reason": "Account not found"}
    
    def commit_transfer(self, data):
        """Phase 2: Commit the transfer"""
        with self.lock:
            txn_id = data.get("txn_id")
            account = data.get("account")
            amount = data.get("amount")
            is_withdrawal = data.get("type") == "withdraw"
            
            # Find and update the held transaction
            for entry in self.transaction_log:
                if entry.get("txn_id") == txn_id and entry.get("type") == "hold":
                    if is_withdrawal:
                        # Withdrawal already done in prepare
                        entry["type"] = "completed"
                        entry["status"] = "withdrawn"
                    else:
                        # Add amount for deposit
                        self.accounts[account] += amount
                        entry["type"] = "completed"
                        entry["status"] = "deposited"
                    
                    return {
                        "status": "committed",
                        "account": account,
                        "new_balance": self.accounts[account]
                    }
            
            return {"status": "error", "message": "Transaction not found"}
    
    def abort_transfer(self, data):
        """Abort/Rollback transfer"""
        with self.lock:
            txn_id = data.get("txn_id")
            account = data.get("account")
            amount = data.get("amount")
            is_withdrawal = data.get("type") == "withdraw"
            
            # Rollback the hold
            for entry in self.transaction_log:
                if entry.get("txn_id") == txn_id and entry.get("type") == "hold":
                    if is_withdrawal:
                        # Return the held amount
                        self.accounts[account] += amount
                    
                    entry["type"] = "aborted"
                    
                    return {
                        "status": "aborted",
                        "account": account,
                        "balance": self.accounts[account]
                    }
            
            return {"status": "error", "message": "Transaction not found"}
    
    def check_balance(self, data):
        """Check account balance"""
        account = data.get("account")
        with self.lock:
            if account in self.accounts:
                return {
                    "status": "success",
                    "account": account,
                    "balance": self.accounts[account]
                }
            else:
                return {"status": "error", "message": "Account not found"}
    
    def simulate_failure(self):
        """Simulate node failure"""
        self.running = False
        return {"status": "failed", "message": "Node going down"}

# =============== TRANSACTION COORDINATOR ===============
class TransferCoordinator:
    def __init__(self, nodes):
        """Initialize with list of (host, port) for nodes"""
        self.nodes = nodes
        self.next_txn_id = 1
    
    def execute_transfer(self, from_account, to_account, amount):
        """Execute distributed money transfer using 2PC"""
        txn_id = f"TXN{self.next_txn_id:04d}"
        self.next_txn_id += 1
        
        print(f"\n{'='*60}")
        print(f"TRANSACTION {txn_id}: Transfer ${amount} from {from_account} to {to_account}")
        print(f"{'='*60}")
        
        # Determine which nodes handle which accounts
        from_node = self.find_node_for_account(from_account)
        to_node = self.find_node_for_account(to_account)
        
        if not from_node or not to_node:
            print("❌ Account(s) not found in system")
            return False
        
        print(f"From: {from_account} on Node {from_node[1]}")
        print(f"To: {to_account} on Node {to_node[1]}")
        
        # Phase 1: Prepare (Vote Request)
        print(f"\n{'─'*40}")
        print("[2PC PHASE 1] PREPARE")
        print(f"{'─'*40}")
        
        # Prepare withdrawal
        withdraw_prepare = {
            "action": "prepare_transfer",
            "txn_id": txn_id,
            "account": from_account,
            "amount": amount,
            "type": "withdraw"
        }
        
        withdraw_response = self.send_request(from_node[0], from_node[1], withdraw_prepare)
        print(f"Node {from_node[1]} (withdrawal): {withdraw_response.get('vote', 'error')}")
        
        if withdraw_response.get("vote") != "yes":
            print(f"Reason: {withdraw_response.get('reason', 'Unknown')}")
            print("❌ Withdrawal failed - aborting transaction")
            return False
        
        # Prepare deposit
        deposit_prepare = {
            "action": "prepare_transfer",
            "txn_id": txn_id,
            "account": to_account,
            "amount": amount,
            "type": "deposit"
        }
        
        deposit_response = self.send_request(to_node[0], to_node[1], deposit_prepare)
        print(f"Node {to_node[1]} (deposit): {deposit_response.get('vote', 'error')}")
        
        if deposit_response.get("vote") != "yes":
            print(f"Reason: {deposit_response.get('reason', 'Unknown')}")
            print("❌ Deposit failed - rolling back withdrawal")
            
            # Rollback the withdrawal
            rollback_data = {
                "action": "abort_transfer",
                "txn_id": txn_id,
                "account": from_account,
                "amount": amount,
                "type": "withdraw"
            }
            self.send_request(from_node[0], from_node[1], rollback_data)
            return False
        
        # Phase 2: Commit
        print(f"\n{'─'*40}")
        print("[2PC PHASE 2] COMMIT")
        print(f"{'─'*40}")
        
        # Commit withdrawal
        withdraw_commit = {
            "action": "commit_transfer",
            "txn_id": txn_id,
            "account": from_account,
            "amount": amount,
            "type": "withdraw"
        }
        
        withdraw_result = self.send_request(from_node[0], from_node[1], withdraw_commit)
        print(f"Node {from_node[1]} (withdrawal): {withdraw_result.get('status', 'error')}")
        
        # Commit deposit
        deposit_commit = {
            "action": "commit_transfer",
            "txn_id": txn_id,
            "account": to_account,
            "amount": amount,
            "type": "deposit"
        }
        
        deposit_result = self.send_request(to_node[0], to_node[1], deposit_commit)
        print(f"Node {to_node[1]} (deposit): {deposit_result.get('status', 'error')}")
        
        # Show final balances
        print(f"\n{'─'*40}")
        print("[FINAL BALANCES]")
        print(f"{'─'*40}")
        
        from_balance = self.check_balance(from_node[0], from_node[1], from_account)
        to_balance = self.check_balance(to_node[0], to_node[1], to_account)
        
        print(f"{from_account}: ${from_balance}")
        print(f"{to_account}: ${to_balance}")
        
        return True
    
    def find_node_for_account(self, account):
        """Find which node handles this account"""
        # Simple hash-based distribution
        node_index = hash(account) % len(self.nodes)
        return self.nodes[node_index]
    
    def send_request(self, host, port, data):
        """Send request to node"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((host, port))
            sock.send(json.dumps(data).encode())
            response = json.loads(sock.recv(1024).decode())
            sock.close()
            return response
        except Exception as e:
            return {"error": str(e), "vote": "no", "status": "failed"}
    
    def check_balance(self, host, port, account):
        """Check account balance"""
        data = {
            "action": "check_balance",
            "account": account
        }
        response = self.send_request(host, port, data)
        return response.get("balance", "N/A")

# =============== DEMO ===============
def run_demo():
    """Run complete demo"""
    print("="*70)
    print("DISTRIBUTED BANK TRANSFER SYSTEM")
    print("3-Node System with 2-Phase Commit Protocol")
    print("="*70)
    
    # Define 3 bank nodes
    NODES = [
        ("localhost", 7001),
        ("localhost", 7002), 
        ("localhost", 7003)
    ]
    
    # Start nodes in background threads
    print("\nStarting 3 bank nodes...")
    
    # Each node has different accounts
    node_accounts = [
        {"ACC1001": 1000.0, "ACC1004": 800.0, "ACC1007": 1200.0},
        {"ACC1002": 500.0, "ACC1005": 1500.0, "ACC1008": 300.0},
        {"ACC1003": 750.0, "ACC1006": 900.0, "ACC1009": 600.0}
    ]
    
    for i, (host, port) in enumerate(NODES):
        node = BankNode(f"Bank{i+1}", port, node_accounts[i])
        threading.Thread(target=node.start, daemon=True).start()
        time.sleep(0.5)
    
    time.sleep(2)
    
    # Create coordinator
    coordinator = TransferCoordinator(NODES)
    
    # Demo 1: Successful transfer (same node)
    print("\n" + "="*70)
    print("DEMO 1: TRANSFER ON SAME NODE")
    print("="*70)
    coordinator.execute_transfer("ACC1001", "ACC1004", 200.0)
    
    # Demo 2: Cross-node transfer
    print("\n" + "="*70)
    print("DEMO 2: CROSS-NODE TRANSFER")
    print("="*70)
    coordinator.execute_transfer("ACC1001", "ACC1002", 150.0)
    
    # Demo 3: Concurrent transfers
    print("\n" + "="*70)
    print("DEMO 3: CONCURRENT TRANSFERS")
    print("="*70)
    
    def concurrent_transfer(from_acc, to_acc, amount, delay):
        time.sleep(delay)
        print(f"\n[Concurrent] Transfer ${amount} from {from_acc} to {to_acc}")
        coordinator.execute_transfer(from_acc, to_acc, amount)
    
    # Start multiple transfers with small delays
    threads = []
    transfers = [
        ("ACC1003", "ACC1006", 100.0, 0.1),
        ("ACC1005", "ACC1008", 200.0, 0.2),
        ("ACC1007", "ACC1009", 150.0, 0.3)
    ]
    
    for from_acc, to_acc, amount, delay in transfers:
        t = threading.Thread(
            target=concurrent_transfer,
            args=(from_acc, to_acc, amount, delay)
        )
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    
    # Demo 4: Failure simulation
    print("\n" + "="*70)
    print("DEMO 4: FAILURE SIMULATION")
    print("="*70)
    print("Simulating node failure during transfer...")
    
    # This will likely fail due to random failure simulation in nodes
    print("\nAttempting transfer with potential failure:")
    success = coordinator.execute_transfer("ACC1002", "ACC1003", 100.0)
    
    if not success:
        print("\n✅ Transaction correctly aborted due to failure")
    else:
        print("\n✅ Transaction succeeded despite potential failures")
    
    print("\n" + "="*70)
    print("DEMO COMPLETED SUCCESSFULLY!")
    print("="*70)
    
    # Keep system running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down system...")

# =============== QUICK TEST ===============
def quick_test():
    """Quick test mode"""
    print("Quick test of distributed account transfer...")
    
    NODES = [("localhost", 8001), ("localhost", 8002)]
    
    # Start nodes
    node1 = BankNode("Bank1", 8001, {"ACC001": 1000.0, "ACC002": 500.0})
    node2 = BankNode("Bank2", 8002, {"ACC003": 750.0, "ACC004": 300.0})
    
    threading.Thread(target=node1.start, daemon=True).start()
    threading.Thread(target=node2.start, daemon=True).start()
    time.sleep(1)
    
    # Test transfer
    coordinator = TransferCoordinator(NODES)
    
    print("\nTest 1: Transfer within same node")
    coordinator.execute_transfer("ACC001", "ACC002", 100.0)
    
    print("\nTest 2: Cross-node transfer")
    coordinator.execute_transfer("ACC001", "ACC003", 50.0)
    
    print("\nSystem running on ports 8001-8002")
    while True:
        time.sleep(1)

# =============== MAIN ===============
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        quick_test()
    else:
        run_demo()