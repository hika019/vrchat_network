# -*- coding: utf-8 -*-

# Step 1. We begin with creating a Configuration, which contains the username and password for authentication.
import vrchatapi
from vrchatapi.api import authentication_api
from vrchatapi.exceptions import UnauthorizedException
from vrchatapi.models.two_factor_auth_code import TwoFactorAuthCode
from vrchatapi.models.two_factor_email_code import TwoFactorEmailCode


from vrchatapi.api.friends_api import FriendsApi
from vrchatapi.api.worlds_api import WorldsApi
from vrchatapi.api.instances_api import InstancesApi

from neo4j import GraphDatabase, basic_auth

import os
from dotenv import load_dotenv
import time
import json
from datetime import date, datetime

# neo4j serverに接続するdriverの設定
driver = GraphDatabase.driver('neo4j://localhost:7687', auth=('neo4j', 'hogehoge123'))

def location_to_world_and_instance(location_id:str):
    """locationをworld_idとinstance_idに分離

    Parameters
    ----------
    location_id : str
        DESCRIPTION.

    Returns
    -------
    str
        world_id.
    str
        instance_id.

    """
    locations = location_id.split(":",1)
    return locations[0], locations[1]

def json_serial(obj):
    # 日付型の場合には、文字列に変換します
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()

def to_dict(data):
    data=vars(data)
    dist={}
    for key in data.keys():
        if key[0]!="_":
            continue
        dist[key[1:]]=data[key]
    return dist

def to_str(data):
    data = to_dict(data)
    
    s = ""
    for i, key in enumerate(data.keys()):
        if key == "unity_packages":
            continue
        print(data[key], type(data[key]))
        s+=key+":"
        
        if isinstance(data[key], (datetime, date)):
            s+='"'+data[key].isoformat()+'"'
        elif isinstance(data[key], dict):
            s+=json.dumps(data[key], default=json_serial)
        elif isinstance(data[key], list):
            s+="["
            for v in data[key]:
                if type(v) is str:
                    s+='"'+v+'",'
                elif type(v) is int:
                    s+=v+','
                elif type(v) is bool:
                    if data[key]==True:
                        s+="true"
                    else:
                        s+="false"
                else:
                    s+=to_str(v)+','
            s+="]"
        elif data[key] is None:
            s+="null"
        elif type(data[key]) is bool:
            if data[key]==True:
                s+="true"
            else:
                s+="false"
        elif type(data[key]) is str:
            s+='"'+data[key].replace("\\n", "\n")+'"'
        elif type(data[key]) is int:
            s+=str(data[key])
        else:
            s+="null"
        
        if i!= len(data.keys()):
            s+=","
        print(s)
    s = "{"+s+"}"
    s = s.replace(",}", "}").replace(",]", "]")
    s = s.replace("{{", "{").replace("}}", "}")
    s = s.replace("{}", "null")
        
    print("property:", s)
    return s


load_dotenv()
configuration = vrchatapi.Configuration(
    username = os.environ["VRC_USERNAME"],
    password = os.environ["VRC_PASSWORD"],
)

# Step 2. VRChat consists of several API's (WorldsApi, UsersApi, FilesApi, NotificationsApi, FriendsApi, etc...)
# Here we enter a context of the API Client and instantiate the Authentication API which is required for logging in.

# Enter a context with an instance of the API client
with vrchatapi.ApiClient(configuration) as api_client:
    # Set our User-Agent as per VRChat Usage Policy
    api_client.user_agent = "FriendLocation/1.0 tmp_email@gmail.com"

    # Instantiate instances of API classes
    auth_api = authentication_api.AuthenticationApi(api_client)

    try:
        # Step 3. Calling getCurrentUser on Authentication API logs you in if the user isn't already logged in.
        current_user = auth_api.get_current_user()
    except UnauthorizedException as e:
        if e.status == 200:
            if "Email 2 Factor Authentication" in e.reason:
                # Step 3.5. Calling email verify2fa if the account has 2FA disabled
                auth_api.verify2_fa_email_code(two_factor_email_code=TwoFactorEmailCode(input("Email 2FA Code: ")))
            elif "2 Factor Authentication" in e.reason:
                # Step 3.5. Calling verify2fa if the account has 2FA enabled
                auth_api.verify2_fa(two_factor_auth_code=TwoFactorAuthCode(input("2FA Code: ")))
            current_user = auth_api.get_current_user()
        else:
            print("Exception when calling API: %s\n", e)
    except vrchatapi.ApiException as e:
        print("Exception when calling API: %s\n", e)

    print("Logged in as:", current_user.display_name)
    
    
    
    
    while(True):
        ins = InstancesApi(api_client)
        current_user = auth_api.get_current_user()

        n_query = 'MERGE (me:USER {id:"'+current_user.id+'"})ON CREATE SET me.name="'+current_user.display_name+'"'
        with driver.session() as session:
            session.run(n_query)

        try:
            if current_user.presence.instance != "offline":
                instance = ins.get_instance(world_id=current_user.presence.world, instance_id=current_user.presence.instance)
        
                instance = instance
                world=instance.world
                with driver.session() as session:
                    n_query = 'MERGE (me:USER {id:"'+current_user.id+'"})ON CREATE SET me.name="'+current_user.display_name+'"'\
                            'MERGE (in:INSTANCE {id:"'+instance.id+'"})ON CREATE SET in.create_at=datetime()'\
                            'MERGE (w:WORLD {id:"'+world.id+'"})ON CREATE SET w.name="'+world.name+'", w.image_url="'+world.image_url+'"'
                    session.run(n_query)

                    r_query = 'MATCH (me:USER) WHERE me.id="'+current_user.id+'"'\
                            'MATCH (instance:INSTANCE) WHERE instance.id="'+instance.id+'"'\
                            'MATCH (w:WORLD) WHERE w.id="'+world.id+'"'\
                            "MERGE (me)-[r:JOIN]->(instance) ON CREATE SET r.fast_time=datetime(), r.last_time=datetime() ON MATCH SET r.last_time=datetime()"\
                            "MERGE (instance)<-[:INSTANCES{id:'"+instance.id+"'}]-(w)"\
                            
                    session.run(r_query)
        except:
            pass
        friends = FriendsApi(api_client)
        for friend in friends.get_friends():
            print(friend.display_name)
            if friend.location in ["private", "offline"]:
                continue
            print(friend.location, type(friend.location))
            if friend.location=="traveling":
                continue
            world_id, instance_id = location_to_world_and_instance(friend.location)
            instance = ins.get_instance(world_id=world_id, instance_id=instance_id)
            world=instance.world
            with driver.session() as session:
                n_query = 'MERGE (friend:USER {id:"'+friend.id+'"})ON CREATE SET friend.name="'+friend.display_name+'"'\
                        'MERGE (in:INSTANCE {id:"'+instance.id+'"})ON CREATE SET in.create_at=datetime()'\
                        'MERGE (w:WORLD {id:"'+world.id+'"})ON CREATE SET w.name="'+world.name+'", w.image_url="'+world.image_url+'"'
                
                
                r_query = 'MATCH (friend:USER) WHERE friend.id="'+friend.id+'"'\
                        'MATCH (instance:INSTANCE) WHERE instance.id="'+instance.id+'"'\
                        'MATCH (w:WORLD) WHERE w.id="'+world.id+'"'\
                        'MATCH (me:USER) WHERE me.id="'+current_user.id+'"'\
                        "MERGE (instance)<-[r1:INSTANCES{id:'"+instance.id+"'}]-(w)"\
                        "MERGE (friend)-[r:JOIN]->(instance)ON CREATE SET r.fast_time=datetime(), r.last_time=datetime() ON MATCH SET r.last_time=datetime()"\
                        "MERGE (friend)-[f1:FRIEND]->(me)-[f2:FRIEND]->(friend) ON CREATE SET f1.from=datetime(), f2.from=datetime()"
                session.run(n_query)
                print(r_query)
                session.run(r_query)
        
        print("executed:",datetime.now())
        time.sleep(60*2)
        
        