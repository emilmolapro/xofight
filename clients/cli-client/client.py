import asyncio, json, websockets

quit_key = 'q'
#normalize strings
ROOM_ID = input("Room ID: ").strip()
USERNAME = input("Username: ").strip()

async def run():
    uri = "ws://127.0.0.1:8003/ws"

    #with handles error and sizing automatically
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"command":"JOIN_ROOM","roomId":ROOM_ID,"username":USERNAME}))
        print(f"Joined. Type moves as 0..8. Type '{quit_key}' to quit.")

        async def receiver():
            try:
                while True:
                    #wait for a message from the other end
                    message = await ws.recv()
                    #indicate it's coming from server
                    print("<--", message)
            except:
                #avoid errors, maybe will handle later
                pass

        async def sender():
            while True:
                #indicate we're talking about a game move
                s = input("> ")

                if s.lower == quit_key:
                    break

                if s.isdigit():
                    await ws.send(json.dumps({"command": "MAKE_MOVE", "roomId": ROOM_ID,
                                              "username": USERNAME, "cell": int(s)}))
                    #make sure both happen at the same time
                    #without asyncio my program was waiting indefinetly
                    await asyncio.gather(receiver(), sender())

asyncio.run(run())