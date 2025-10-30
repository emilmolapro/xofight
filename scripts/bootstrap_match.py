import sys
import time
import requests

USER_SERVICE = "http://127.0.0.1:8001"
ROOM_SERVICE = "http://127.0.0.1:8002"

def wait_ok(url, tries=20, delay=0.25):
    for _ in range(tries):
        try:
            req = requests.get(url, timeout=1.5)
            if req.ok:
                return True
        except requests.RequestException:
            pass
        time.sleep(delay)
    return False

def main(p1="emil", p2="sara"):
    #make sure service is running
    if not wait_ok(f"{USER_SERVICE}/health"):
        print("[ERR] user-service not reachable at", USER_SERVICE)
        sys.exit(1)
    if not wait_ok(f"{ROOM_SERVICE}/health"):
        print("[ERR] room-service not reachable at", ROOM_SERVICE)
        sys.exit(1)

    #register two default players
    for u in (p1,p2):
        try:
            req = requests.post(url=f"{USER_SERVICE}/register", json={"username": u}, timeout=3)
            #check for errors
            req.raise_for_status()
            #if passed print log
            print(f"[OK ] registered: {u} -> {req.json().get('message', 'ok')}")
        except requests.RequestException as e:
            print(f"[ERR] registering: {u}: {e}")
            sys.exit(1)
    
    #create room with emil
    try:
        req = requests.post(f"{ROOM_SERVICE}/rooms/create", json={"username": p1}, timeout=3)
        req.raise_for_status()

        room = req.json()
        room_id = room["roomId"]
        print(f"[OK ] room created by {p1}: {room_id}")
    except requests.RequestException as e:
        print(f"[ERR] creating room: {e}")
        sys.exit(1)
    
    #check if another played joined -> activate game
    try:
        req = requests.post(f"{ROOM_SERVICE}/rooms/join", json={"roomId": room_id, "username": p2}, timeout=5)
        req.raise_for_status()
        joined = req.json()
        match_id = joined.get("matchId")
        status = joined.get("status")
        print(f"[OK ] {p2} joined room: {room_id} | status={status} | matchId={match_id}")
    except requests.RequestException as e:
        print(f"[ERR] joining room: {e}")
        sys.exit(1)
    
    print("\n--- Ready to play ---")
    print("Open two terminals and run:")
    print(f'  wscat -c ws://127.0.0.1:8003/ws')
    print(f'  {{\"command\":\"JOIN_ROOM\",\"roomId\":\"{room_id}\",\"username\":\"{p1}\"}}')
    print()
    print(f'  wscat -c ws://127.0.0.1:8003/ws')
    print(f'  {{\"command\":\"JOIN_ROOM\",\"roomId\":\"{room_id}\",\"username\":\"{p2}\"}}')
    print("\nThen make moves (cell 0-8):")
    print(f'  {{\"command\":\"MAKE_MOVE\",\"roomId\":\"{room_id}\",\"username\":\"{p1}\",\"cell\":0}}')

if __name__ == "__main__":
    # allow optional CLI args: bootstrap_match.py [player1] [player2]
    args = sys.argv[1:]
    if len(args) >= 2:
        main(args[0], args[1])
    else:
        main()