from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional, Dict, List
from uuid import uuid4
import requests
import json
from json import JSONDecodeError
from starlette.websockets import WebSocketState

USER_SERVICE_URL = "http://127.0.0.1:8001"

app = FastAPI()

@app.get("/health")
def health_check():
    return {"service": "game-service", "status": "ok"}


#-------------------#
#IN MEMORY DATA SETS#
#-------------------#

#key metric matchId
#dictionary for pairing data
matches: Dict[str, dict] = {}

#roomId will list matches
map_rooms_to_match: Dict[str, dict] = {}

#roomId will list active connections
active_connections: Dict[str, List[WebSocket]] = {}

class StartMatchRequest(BaseModel):
    roomId:     str
    players:    list[str]

def initiate_board(number_of_cells: int):  
    return [""] * number_of_cells

#create a match object
@app.post("/game/start")
def start_match(request: StartMatchRequest):

    #initialize a match object
    match_id = "MATCH_" + uuid4().hex[:8]

    #set a board 3X3 -> in total 9 empty cells
    board = initiate_board(number_of_cells=9)

    #create match json
    matches[match_id] = {
        "roomId":   request.roomId,
        "players":  request.players,
        "board":    board,
        "turn":     request.players[0],
        "status":   "ACTIVE",
        "score": {
            request.players[0]: 0,
            request.players[1]: 0,
            "draws": 0,
        }
    }


    map_rooms_to_match[request.roomId] = {
        "matchId": match_id,
        "players": request.players
    }

    if request.roomId not in active_connections:
        active_connections[request.roomId] = []

    return {
        "matchId": match_id,
        "roomId": request.roomId,
        "players": request.players,
        "status": "STARTED"
    }

@app.get("/game/state/{room_id}")
def debug_state(room_id: str):
    state = get_match_state_by_room(room_id)
    if not state:
        raise HTTPException(status_code=404, detail="No state")
    return state

#message to all participants
async def broadcast_room(room_id: str, message: dict):

    #intialize list for closing connections
    dead_connections = []

    for ws in active_connections.get(room_id, []):
        try:
            await ws.send_json(message)
        except Exception:
            dead_connections.append(ws)
    
    #ensure dead connections are no longer active
    for ws in dead_connections:
        active_connections[room_id].remove(ws)

#get the current match state in the room
def get_match_state_by_room(room_id: str):
    room_info = map_rooms_to_match.get(room_id)

    if not room_info:
        return None
    
    match_id = room_info["matchId"]
    match = matches.get(match_id)

    if not match:
        return None
    
    return {
        "roomId": room_id,
        "matchId": match_id,
        "players": match["players"],
        "board": match["board"],
        "turn": match["turn"],
        "status": match["status"],
        "score": match["score"]
    }

def get_match_by_room(room_id: str):
    room_info = map_rooms_to_match.get(room_id)

    if not room_info:
        return None, None
    
    match_id = room_info["matchId"]
    match = matches.get(match_id)

    return match_id, match

#one player gets X, the other gets O
def get_symbol_for_player(match: dict, username: str) -> Optional[str]:
    player_list = match["players"]

    if len(player_list) >= 1 and username == player_list[0]:
        return "X"
    if len(player_list) >= 2 and username == player_list[1]:
        return "O"
    
    #if username in not matched
    return None

#see if there is 3x strike
def check_winners(board: list[str]) -> Optional[str]:
    wins = [
        (0,1,2), (3,4,5), (6,7,8),   #horizontal
        (0,3,6), (1,4,7), (2,5,8),   #vertical
        (0,4,8), (2,4,6)            #diagonal
    ]

    for a,b,c in wins:
        #ensure that 3 empty cells don't count as a win
        if board[a] != "":
            #check if all the cells have the same symbol
            if board[a] == board[b] == board[c]:
                return board[a]
    
    #first time using: all() -> check if all items in list are true [maybe others will find it handy]
    #ensure that the game has finished with no cells left and no winner
    if all(cell != "" for cell in board):
        return "DRAW"
    
    return None

#we can play it as best out of 3 - prepare the next round
def reset_board_for_next_round(match: dict):
    match["board"] = [""] * 9
    match["status"] = "ACTIVE"

#message after a move
def build_board_state_message(room_id:str, match_id: str, match:dict) -> dict:
    return {
        "type": "BOARD_UPDATE",
        "roomId": room_id,
        "matchId": match_id,
        "board": match["board"],
        "turn": match["turn"],
        "status": match["status"],
        "score": match["score"],
    }

def report_result(player1: str, player2: str, winner:str | None):
    try:
        requests.post(
            f"{USER_SERVICE_URL}/reportResult",
            json={"player1": player1, "player2": player2, "winner": winner},
            timeout=3
        )
    except requests.RequestException:
        pass

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):

    #accept the connection
    await ws.accept()

    current_room_id = None
    current_username = None

    try:
        while True:
            #safe check to see if the json command is correct
            #any mistyping crashed the app before
            try:
                text = await ws.receive_text()
                #ignore empty calls
                if not text or not text.strip():
                    continue
                try:
                    data = json.loads(text)
                except JSONDecodeError:
                    #note to self: remember await!
                    await ws.send_json({"type":"ERROR","error":"Invalid JSON"})
                    #ensure no crash
                    continue
            #if client closed / sent non-text -> keep the loop running
            except Exception:
                if ws.application_state != WebSocketState.CONNECTED:
                    break
                await ws.send_json({"type":"ERROR","error":"Failed to read message"})
                #ensure no crash
                continue
            
            #data moved to try loop above to prevent crash 
            #data = await ws.receive_json()
            command = data.get("command")

            if command == "JOIN_ROOM":
                room_id = data.get("roomId")
                username = data.get("username")

                if room_id is None:
                    await ws.send_json({"type": "ERROR", "error": "Room ID is required"})
                    continue
                
                if username is None:
                    await ws.send_json({"type": "ERROR", "error": "Username is required"})
                    continue

                #assign to the socket if we passed the tests
                current_room_id = room_id
                current_username = username

                #activate the socket by storing it in the list
                if room_id not in active_connections:
                    active_connections[room_id] = []
                active_connections[room_id].append(ws)

                #send state to the user that joined
                state = get_match_state_by_room(room_id=room_id)
                await ws.send_json({
                    "type": "JOINED_ROOM",
                    "roomId": room_id,
                    "you": username,
                    "matchState": state
                })

                #let everyone know that the user has joined
                await broadcast_room(room_id=room_id, message={
                    "type":     "PLAYER_JOINED",
                    "roomId":   room_id,
                    "username": username
                })
            elif command == "MAKE_MOVE":
                room_id = data.get("roomId")
                username = data.get("username")
                cell = data.get("cell")

                if not room_id:
                    await ws.send_json({"type": "ERROR", "error": "Room ID is required"})
                    continue
                if not username:
                    await ws.send_json({"type": "ERROR", "error": "Username is required"})
                    continue
                if cell is None:
                    await ws.send_json({"type": "ERROR", "error": "Cell is required"})
                    continue

                match_id, match = get_match_by_room(room_id=room_id)
                if not match:
                    await ws.send_json({"type": "ERROR", "error": "No active match in this room"})
                    continue

                symbol = get_symbol_for_player(match=match,username=username)
                if not symbol:
                    await ws.send_json({"type": "ERROR", "error": "You are not a player in this match!"})
                    continue

                if match["turn"] != username:
                    await ws.send_json({"type": "ERROR", "error": "Please wait for your turn"})
                    continue

                #check if the cell is empty & valid
                try:
                    cell = int(cell)
                except Exception:
                    await ws.send_json({"type": "ERROR", "error": "Cell value must range between 0-8"})
                    continue

                if cell < 0 or cell > 8:
                    await ws.send_json({"type": "ERROR", "error": f"Cell {cell} is invalid [range: 0-8]"})
                    continue

                if match["board"][cell] != "":
                    await ws.send_json({"type": "ERROR", "error": "Cell is taken"})
                    continue

                #if we passed so far - make the move
                match["board"][cell] = symbol

                #check if the move resulted in a win
                result = check_winners(match["board"])

                #if it didn't - pass the turn to next player
                if not result:
                    p1,p2 = match["players"][0], match["players"][1]
                    match["turn"] = p2 if match["turn"] == p1 else p1

                    await broadcast_room(room_id=room_id,message=build_board_state_message(room_id,match_id,match))

                elif result == "DRAW":
                    match["score"]["draws"] += 1
                    match["status"] = "ROUND_OVER"
                    p1,p2 = match["players"]
                    report_result(p1,p2,None)

                    await broadcast_room(room_id, {
                        "type": "ROUND_END",
                        "roomId": room_id,
                        "matchId": match_id,
                        "result": "DRAW",
                        "board": match["board"],
                        "score": match["score"]
                    })
                
                else:
                    #figure if the first or second player won the game
                    #remember the first player gets the X
                    winner_username = match["players"][0] if result == "X" else match["players"][1]
                    loser_username = match["players"][1] if result == "X" else match["players"][0]

                    match["score"][winner_username] += 1
                    match["status"] = "ROUND_OVER"
                    p1,p2 = match["players"]
                    report_result(p1,p2,winner_username)

                    #notify everybody
                    await broadcast_room(room_id, {
                        "type":     "ROUND_END",
                        "roomId":   room_id,
                        "matchId":  match_id,
                        "result":   "WIN",
                        "winner":   winner_username,
                        "loser":    loser_username,
                        "board":    match["board"],
                        "score":    match["score"]})



            else:
                await ws.send_json({"type": "ERROR", "error": f"Unknown command {command}"})
    
    #when client disconnects - remove
    except WebSocketDisconnect:
        #check if current room id exists
        if current_room_id:
            #check if it's active
            if current_room_id in active_connections:
                if ws in active_connections[current_room_id]:
                    active_connections[current_room_id].remove(ws)

                    #notify everyone in the room
                    await broadcast_room(current_room_id,{
                        "type": "PLAYER_LEFT",
                        "roomId": current_room_id,
                        "username": current_username})
                    


#command run:   {"command":"JOIN_ROOM","roomId":"ROOMID","username":"emil"}
#               {"command":"JOIN_ROOM","roomId":"ROOMID","username":"sara"}
#               {"command":"MAKE_MOVE","roomId":"ROOMID","username":"emil","cell":CELL}
#               {"command":"MAKE_MOVE","roomId":"ROOMID","username":"sara","cell":CELL}