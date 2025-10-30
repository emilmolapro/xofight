from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from uuid import uuid4
import requests


app = FastAPI()

#check if service runs
@app.get("/health")
def health_check():
    return {"service": "room-service", "status": "ok"}

#in memory data set
rooms = {}

GAME_SERVICE_URL = "http://127.0.0.1:8003"

class CreateRoomRequest(BaseModel):
    username: str

@app.post("/rooms/create")
def create_room(request: CreateRoomRequest):
    
    #normalize username
    username = request.username.strip()

    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    
    room_id = "ROOM_" + uuid4().hex[:6]

    rooms[room_id] = {
        "players":  [username],
        "status":   "WAITING",
        "matchId":  None
    }

    return {
        "roomId":   room_id,
        "players":  rooms[room_id]["players"],
        "status":   rooms[room_id]["status"]
    }

class JoinRoomRequest(BaseModel):
    roomId:     str
    username:   str

def json_room(room_id):
    room = rooms[room_id]
    return {
        "roomId":   room_id,
        "players":  room["players"],
        "status":   room["status"],
        "matchId":  room["matchId"]
    }

#player enters a room
@app.post("/rooms/join")
def join_room(req: JoinRoomRequest):
    room_id = req.roomId
    username = req.username.strip()

    if room_id not in rooms:
        raise HTTPException(status_code=404, detail=f"Room {room_id} not found!")
    
    room = rooms[room_id]

    #user is already in room
    if username in room["players"]:
        return json_room(room_id=room_id)
    
    #is place in room?
    if len(room["players"]) >=2:
        raise HTTPException(status_code=400, detail="Room is full!")
    
    room["players"].append(username)

    if len(room["players"]) == 2:
        p1, p2 = room["players"][0],room["players"][1]

        start_payload = {
            "roomId": room_id,
            "players": [p1,p2]
        }

        try:
            response = requests.post(
                f"{GAME_SERVICE_URL}/game/start",
                json=start_payload,
                timeout=5
            )
            response.raise_for_status()
        except requests.RequestException as error:
            room["status"] = "ERROR_STARTING_MATCH"
            room["matchId"] = None
            raise HTTPException(status_code=500, detail=f"Couldn't start game: {error}")
        
        data = response.json()
        room["status"] = "ACTIVE"
        room["matchId"] = data.get("matchId")

    return json_room(room_id=room_id)

@app.get("/rooms/{roomId}")
def get_room(roomId: str):
    if roomId not in rooms:
        raise HTTPException(status_code=404, detail=f"Room {roomId} not found!")
    return rooms[roomId]    
