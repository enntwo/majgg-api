from collections import UserDict
from fastapi import FastAPI

import asyncio
import hashlib
import hmac
import logging
import random
import uuid
import json
from optparse import OptionParser

import aiohttp
import os

from ms.base import MSRPCChannel
from ms.rpc import Lobby
import ms.protocol_pb2 as pb
from google.protobuf.json_format import MessageToJson, MessageToDict

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)

MS_HOST = "https://game.maj-soul.com"

app = FastAPI()

logged_in = False

cache = {}

@app.on_event("startup")
async def startup_event():
    lobby, channel = await connect()
    await login(lobby, os.environ.get('CN_ACCOUNT_NAME'), os.environ.get('CN_ACCOUNT_PASS'))
    cache["lobby"] = lobby
    cache["channel"] = channel


async def ensure_login():
    #if not lob:
    #    lob, chan = await connect()
    #    await login(lob, os.environ.get('CN_ACCOUNT_NAME'), os.environ.get('CN_ACCOUNT_PASS'))
    lobby = cache["lobby"]
    channel = cache["channel"]
    try:
        heatbeat = pb.ResCommon()
        res_heatbeat = await lobby.heatbeat(heatbeat)
        if not res_heatbeat.error is None:
            logging.info("HeatBeat ERROR: {}".format(res_heatbeat.error))

        loginbeat = pb.ResCommon()
        res_loginbeat = await lobby.heatbeat(loginbeat)
        if not res_loginbeat.error is None:
            logging.info("LoginBeat ERROR: {}".format(res_loginbeat.error))
        
    except Exception as e:
        logging.info("Ensure_login ERROR: {}".format(e))
        if not channel is None:
            channel.close()
        cache.pop("lobby", None)
        cache.pop("channel", None)
        await startup_event()
        return cache["lobby"]
    
    return cache["lobby"]
    #     if not logged_in:
    #         global lobby, channel = await connect()
    #         await login(lobby, os.environ.get('CN_ACCOUNT_NAME'), os.environ.get('CN_ACCOUNT_PASS'))
    #         logged_in = True
    #     else:

    # except:
    #     try:
    #         global lobby, channel = await connect()
    #         await login(lobby, os.environ.get('CN_ACCOUNT_NAME'), os.environ.get('CN_ACCOUNT_PASS'))
    #         logged_in = True
    #     except:
    #         return False



@app.get("/")
async def root():
    return {"message": "Hello world"}

@app.get("/login")
async def login():
    lobby = await ensure_login()
    return {"message": "Success"}    

@app.get("/logout")
async def logout():
    # lobby = await ensure_login()
    lobby = cache["lobby"]
    logout = pb.ReqLogout()
    res = await lobby.logout(logout)
    return {"message": "{}".format(res.error)}    

@app.get("/sample")
async def sample():
    lobby, channel = await connect()
    await login(lobby, os.environ.get('CN_ACCOUNT_NAME'), os.environ.get('CN_ACCOUNT_PASS'))

    #game_log = await load_and_process_game_log(lobby, "210110-39822d27-fa68-4315-ad33-e60074c682e1")
    #logging.info("game {} result : \n{}".format(game_log.head.uuid, game_log.head.result))

    game_json =  await game_log_as_json(lobby, "210110-39822d27-fa68-4315-ad33-e60074c682e1")

    await channel.close()

    return game_json 

@app.get("/test")
async def test():
    lobby = cache["lobby"]

    #game_log = await load_and_process_game_log(lobby, "210110-39822d27-fa68-4315-ad33-e60074c682e1")
    #logging.info("game {} result : \n{}".format(game_log.head.uuid, game_log.head.result))

    game_json =  await game_log_as_json(lobby, "210110-39822d27-fa68-4315-ad33-e60074c682e1")

    return game_json 

@app.get("/record/{uuid}")
async def record(uuid):
    lobby, channel = await connect()
    await login(lobby, os.environ.get('CN_ACCOUNT_NAME'), os.environ.get('CN_ACCOUNT_PASS'))

    #game_log = await load_and_process_game_log(lobby, "210110-39822d27-fa68-4315-ad33-e60074c682e1")
    #logging.info("game {} result : \n{}".format(game_log.head.uuid, game_log.head.result))

    game_json =  await game_log_as_json(lobby, uuid)

    await channel.close()

    return game_json 

async def connect():
    async with aiohttp.ClientSession() as session:
        async with session.get("{}/1/version.json".format(MS_HOST)) as res:
            version = await res.json()
            logging.info(f"Version: {version}")

            version = version["version"]

        async with session.get("{}/1/v{}/config.json".format(MS_HOST, version)) as res:
            config = await res.json()
            logging.info(f"Config: {config}")

            url = config["ip"][0]["region_urls"][1]

        async with session.get(url + "?service=ws-gateway&protocol=ws&ssl=true") as res:
            servers = await res.json()
            logging.info(f"Available servers: {servers}")

            servers = servers["servers"]
            server = random.choice(servers)
            endpoint = "wss://{}/".format(server)

    logging.info(f"Chosen endpoint: {endpoint}")
    channel = MSRPCChannel(endpoint)

    lobby = Lobby(channel)

    await channel.connect(MS_HOST)
    logging.info("Connection was established")

    return lobby, channel


async def login(lobby, username, password):
    logging.info("Login with username and password")

    uuid_key = str(uuid.uuid1())

    req = pb.ReqLogin()
    req.account = username
    req.password = hmac.new(b"lailai", password.encode(), hashlib.sha256).hexdigest()
    req.device.is_browser = True
    req.random_key = uuid_key
    req.gen_access_token = True
    req.currency_platforms.append(2)

    res = await lobby.login(req)
    token = res.access_token
    if not token:
        logging.error("Login Error:")
        logging.error(res)
        return False

    return True


async def load_game_logs(lobby):
    logging.info("Loading game logs")

    records = []
    current = 1
    step = 30
    req = pb.ReqGameRecordList()
    req.start = current
    req.count = step
    res = await lobby.fetch_game_record_list(req)
    records.extend([r.uuid for r in res.record_list])

    return records


async def load_and_process_game_log(lobby, uuid):
    logging.info("Loading game log")

    req = pb.ReqGameRecord()
    req.game_uuid = uuid
    res = await lobby.fetch_game_record(req)

    record_wrapper = pb.Wrapper()
    record_wrapper.ParseFromString(res.data)

    

    game_details = pb.GameDetailRecords()
    game_details.ParseFromString(record_wrapper.data)

    #jsonOut = MessageToDict(game_details)
    # logging.info(jsonOut)

    for record in game_details.records:
        logging.info(MessageToDict(record))

    game_records_count = len(game_details.records)
    logging.info("Found {} game records".format(game_records_count))

    round_record_wrapper = pb.Wrapper()
    is_show_new_round_record = False
    is_show_discard_tile = False
    is_show_deal_tile = False

    for i in range(0, game_records_count):
        round_record_wrapper.ParseFromString(game_details.records[i])

        if round_record_wrapper.name == ".lq.RecordNewRound" and not is_show_new_round_record:
            logging.info("Found record type = {}".format(round_record_wrapper.name))
            round_data = pb.RecordNewRound()
            round_data.ParseFromString(round_record_wrapper.data)
            print_data_as_json(round_data, "RecordNewRound")
            is_show_new_round_record = True

        if round_record_wrapper.name == ".lq.RecordDiscardTile" and not is_show_discard_tile:
            logging.info("Found record type = {}".format(round_record_wrapper.name))
            discard_tile = pb.RecordDiscardTile()
            discard_tile.ParseFromString(round_record_wrapper.data)
            print_data_as_json(discard_tile, "RecordDiscardTile")
            is_show_discard_tile = True

        if round_record_wrapper.name == ".lq.RecordDealTile" and not is_show_deal_tile:
            logging.info("Found record type = {}".format(round_record_wrapper.name))
            deal_tile = pb.RecordDealTile()
            deal_tile.ParseFromString(round_record_wrapper.data)
            print_data_as_json(deal_tile, "RecordDealTile")
            is_show_deal_tile = True

    return res

async def game_log_as_json(lobby, uuid):
    logging.info("Loading game log")

    jsonOutput = {}

    req = pb.ReqGameRecord()
    req.game_uuid = uuid
    res = await lobby.fetch_game_record(req)

    #head = pb.ResGameRecord()
    #head.ParseFromString(res)

    record_wrapper = pb.Wrapper()
    record_wrapper.ParseFromString(res.data)

    game_details = pb.GameDetailRecords()
    game_details.ParseFromString(record_wrapper.data)

    game_records_count = len(game_details.records)
    round_record_wrapper = pb.Wrapper()

    jsonOutput["Game"] = MessageToDict(res)["head"]
    jsonOutput["Game"]["Rounds"] = []

    round = -1

    for i in range(0, game_records_count):
        round_record_wrapper.ParseFromString(game_details.records[i])

        if round_record_wrapper.name == ".lq.RecordNewRound":
            round += 1
            round_data = pb.RecordNewRound()
            round_data.ParseFromString(round_record_wrapper.data)
            #jsonStr += json.dumps(MessageToDict(round_data))
            #jsonOutput[f"Round{i}"] = MessageToDict(round_data)
            jsonOutput["Game"]["Rounds"].append(MessageToDict(round_data))
            jsonOutput["Game"]["Rounds"][round]["Tile"] = []
            # jsonOutput.update(MessageToDict(round_data))
            #jsonParts.append(list(MessageToDict(round_data).items()))

        elif round_record_wrapper.name == ".lq.RecordDiscardTile":
            discard_tile = pb.RecordDiscardTile()
            discard_tile.ParseFromString(round_record_wrapper.data)
            #jsonOutput[f"Discard{i}"] = MessageToDict(discard_tile)
            jsonOutput["Game"]["Rounds"][round]["Tile"].append(MessageToDict(discard_tile))

        elif round_record_wrapper.name == ".lq.RecordDealTile":
            deal_tile = pb.RecordDealTile()
            deal_tile.ParseFromString(round_record_wrapper.data)
            #jsonOutput[f"Deal{i}"] = MessageToDict(deal_tile)
            jsonOutput["Game"]["Rounds"][round]["Tile"].append(MessageToDict(deal_tile))

        elif round_record_wrapper.name == ".lq.RecordChiPengGang":
            call_tile = pb.RecordChiPengGang()
            call_tile.ParseFromString(round_record_wrapper.data)
            #jsonOutput[f"Call{i}"] = MessageToDict(call_tile)
            

        elif round_record_wrapper.name == ".lq.RecordHule":
            # data = bytearray(round_record_wrapper.data, "utf-8")
            round_result = pb.RecordHuleInfo()
            # round_result.ParseFromString(round_record_wrapper.data)
            # round_result.ParseFromString((round_record_wrapper.data).encode('utf-8').strip())
            # jsonOutput[f"RoundResult{i}"] = MessageToDict(round_result)

        #else:
        #    jsonOutput[f"UNKNOWN{i}"] = round_record_wrapper.name

    return jsonOutput

def print_data_as_json(data, type):
    json = MessageToJson(data)
    logging.info("{} json {}".format(type, json))