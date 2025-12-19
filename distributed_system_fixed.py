import socket
import json
import threading
import time
import sys
import uuid

# ==========================================================
# ACCOUNT
# ==========================================================

class Account:
    def __init__(self, account_id, balance):
        self.account_id = account_id
        self.balance = balance
        self.lock = threading.Lock()

    def __str__(self):
        return f"{self.account_id}: ${self.balance:.2f}"

# ==========================================================
# NODE SERVER
# ==========================================================

class NodeServer:
    def __init__(self, node_id, port_offset):
        self.node_id = node_id
        self.host = "localhost"
        self.port = 6000 + port_offset
        self.accounts = self._init_accounts()
        self.transactions = {}
        self.running = True
        self.is_active = True

        print(f"🖥️  {self.node_id} running on port {self.port}")
        for acc in self.accounts.values():
            print(f"   {acc}")

    def _init_accounts(self):
        if self.node_id == "NODE-1":
            return {
                "ACC001": Account("ACC001", 1000),
                "ACC002": Account("ACC002", 2000)
            }
        elif self.node_id == "NODE-2":
            return {
                "ACC003": Account("ACC003", 1500),
                "ACC004": Account("ACC004", 3000)
            }
        else:
            return {
                "ACC005": Account("ACC005", 500),
                "ACC006": Account("ACC006", 1000)
            }

    # ------------------------------------------------------

    def handle_request(self, data):
        req = json.loads(data)
        action = req.get("action")

        if action == "prepare":
            return json.dumps(self.prepare(req))
        if action == "commit":
            return json.dumps(self.commit(req))
        if action == "rollback":
            return json.dumps(self.rollback(req))
        if action == "status":
            return json.dumps(self.status())
        if action == "crash":
            return json.dumps(self.crash())
        if action == "recover":
            return json.dumps(self.recover())

        return json.dumps({"status": "ERROR"})

    # ------------------------------------------------------
    # 2PC PREPARE
    # ------------------------------------------------------

    def prepare(self, req):
        if not self.is_active:
            return {"status": "ABORT"}

        txn_id = req["transaction_id"]
        fa = req["from_account"]
        ta = req["to_account"]
        amt = req["amount"]

        involved = [a for a in [fa, ta] if a in self.accounts]

        # ✅ FIX: NO_OP TRANSACTION
        if not involved:
            self.transactions[txn_id] = {"status": "NO_OP"}
            return {"status": "READY"}

        locked = []
        for acc_id in involved:
            if self.accounts[acc_id].lock.acquire(False):
                locked.append(acc_id)
            else:
                for l in locked:
                    self.accounts[l].lock.release()
                return {"status": "ABORT"}

        if fa in involved and self.accounts[fa].balance < amt:
            for l in locked:
                self.accounts[l].lock.release()
            return {"status": "ABORT"}

        self.transactions[txn_id] = {
            "status": "PREPARED",
            "from": fa,
            "to": ta,
            "amount": amt,
            "locked": locked
        }

        return {"status": "READY"}

    # ------------------------------------------------------
    # 2PC COMMIT
    # ------------------------------------------------------

    def commit(self, req):
        txn_id = req["transaction_id"]
        txn = self.transactions.get(txn_id)

        # ✅ FIX: Treat missing transaction as NO-OP
        if not txn:
            return {"status": "COMMITTED"}

        if txn["status"] == "NO_OP":
            return {"status": "COMMITTED"}

        if txn["from"] in self.accounts:
            self.accounts[txn["from"]].balance -= txn["amount"]

        if txn["to"] in self.accounts:
            self.accounts[txn["to"]].balance += txn["amount"]

        for acc in txn["locked"]:
            self.accounts[acc].lock.release()

        txn["status"] = "COMMITTED"
        return {"status": "COMMITTED"}

    # ------------------------------------------------------

    def rollback(self, req):
        txn = self.transactions.get(req["transaction_id"])
        if not txn:
            return {"status": "ROLLED_BACK"}

        for acc in txn.get("locked", []):
            self.accounts[acc].lock.release()

        txn["status"] = "ROLLED_BACK"
        return {"status": "ROLLED_BACK"}

    # ------------------------------------------------------

    def status(self):
        return {
            "status": "OK",
            "node": self.node_id,
            "active": self.is_active,
            "accounts": [
                {"id": a.account_id, "balance": a.balance, "locked": a.lock.locked()}
                for a in self.accounts.values()
            ]
        }

    def crash(self):
        self.is_active = False
        return {"status": "CRASHED"}

    def recover(self):
        self.is_active = True
        self.transactions.clear()
        return {"status": "RECOVERED"}

    # ------------------------------------------------------

    def start(self):
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((self.host, self.port))
        s.listen(5)

        while self.running:
            try:
                c, _ = s.accept()
                data = c.recv(4096).decode()
                if data:
                    c.send(self.handle_request(data).encode())
                c.close()
            except:
                pass

# ==========================================================
# COORDINATOR
# ==========================================================

class Coordinator:
    def __init__(self):
        self.nodes = {}
        self.lock = threading.Lock()

    def register(self, node_id, host, port):
        self.nodes[node_id] = (host, port)

    def send(self, node_id, msg):
        try:
            with socket.socket() as s:
                s.connect(self.nodes[node_id])
                s.send(json.dumps(msg).encode())
                return json.loads(s.recv(4096).decode())
        except:
            return {"status": "ERROR"}

    def execute_transaction(self, fa, ta, amt, name):
        txn_id = f"TXN-{uuid.uuid4().hex[:6]}"

        with self.lock:
            print(f"\n🚀 {name}: {fa} -> {ta} (${amt})")

        # PREPARE
        results = {}
        for n in self.nodes:
            res = self.send(n, {
                "action": "prepare",
                "transaction_id": txn_id,
                "from_account": fa,
                "to_account": ta,
                "amount": amt
            })
            results[n] = res

        if not all(r["status"] == "READY" for r in results.values()):
            for n in self.nodes:
                self.send(n, {"action": "rollback", "transaction_id": txn_id})
            return "ABORTED"

        # COMMIT
        commits = []
        for n in self.nodes:
            res = self.send(n, {"action": "commit", "transaction_id": txn_id})
            commits.append(res["status"] == "COMMITTED")

        return "COMMITTED" if all(commits) else "PARTIAL_COMMIT"

# ==========================================================
# MAIN
# ==========================================================

def run_node(node_id):
    ports = {"NODE-1": 1, "NODE-2": 2, "NODE-3": 3}
    node = NodeServer(node_id, ports[node_id])
    node.start()

def main():
    if len(sys.argv) < 3:
        print("Usage:")
        print(" python distributed_system_fixed.py node NODE-1")
        print(" python distributed_system_fixed.py coordinator")
        return

    if sys.argv[1] == "node":
        run_node(sys.argv[2])

if __name__ == "__main__":
    main()
