from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

app = FastAPI()

#in memory data set
#key field: username
players = {}

class RegisterRequest(BaseModel):
    username: str

def json_create_user(message, username, wins=0, losses=0, draws=0):
    return {
        "message": message,
        "user": {
            "username": username,
            "wins": wins,
            "losses": losses,
            "draws": draws
        }
    }

def json_get_user(username):
    return {
        "username": username,
        "wins": players[username]["wins"],
        "losses": players[username]["losses"],
        "draws": players[username]["draws"],
    }

#Check if service is running [in parallel]
@app.get("/health")
def health_check():
    return {"service": "user-service", "status": "ok"}

#Create user
@app.post("/register")
def register_user(request: RegisterRequest):
    #normalize usernames
    username = request.username.strip()

    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    
    if username in players:
        wins = players[username]["wins"]
        losses = players[username]["losses"]
        draws = players[username]["draws"]
        return json_create_user(message="already registered", username=username,
                            wins=wins, losses=losses, draws=draws)
    
    players[username] = {
        "wins": 0,
        "losses": 0,
        "draws": 0,
    }

    return json_create_user(message="registered successfully", username=username)

#Get user
@app.get("/users/{username}")
def get_user_by_username(username: str):
    if username not in players:
        raise HTTPException(status_code=404, detail=f'User {username} not found!')
    
    return json_get_user(username=username)

class ReportResultRequest(BaseModel):
    player1:    str
    player2:    str
    winner:     Optional[str] = None

def player_not_found_exception(player):
    if player not in players:
        raise HTTPException(status_code=400, detail=f"Player not found!")

#Result at the end of the match
@app.post("/reportResult")
def report_result(request: ReportResultRequest):
    p1, p2, winner = request.player1, request.player2, request.winner

    #check if players exist
    player_not_found_exception(p1)
    player_not_found_exception(p2)

    #if it's a draw
    if winner is None:
        players[p1]["draws"] += 1
        players[p2]["draws"] += 1
        return {"status": "draw_recorded"}
    
    #if winner is not one of the players
    if winner not in [p1,p2]:
        raise HTTPException(status_code=400, detail=f"Winner {winner} is not part of the game")
    
    loser = p2 if winner == p1 else p1

    players[winner]["wins"] += 1
    players[loser]["losses"] += 1

    return {"status": "result_recorded"}

