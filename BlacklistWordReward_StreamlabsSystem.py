# -*- coding: utf-8 -*-

#---------------------------
#   Import Libraries
#---------------------------
import clr, codecs, json, os, re, sys, threading, datetime, math

clr.AddReference("IronPython.Modules.dll")

sys.path.append(os.path.dirname(os.path.realpath(__file__)) + r"\References")
clr.AddReference(r"TwitchLib.PubSub.dll")
from TwitchLib.PubSub import TwitchPubSub

#---------------------------
#   [Required] Script Information
#---------------------------
ScriptName = "Blacklist Word Reward"
Website = "https://www.twitch.tv/EncryptedThoughts"
Description = "Script to allow users to blacklist a word as a channel point reward."
Creator = "EncryptedThoughts"
Version = "2.0.0.0"

#---------------------------
#   Define Global Variables
#---------------------------
SettingsFile = os.path.join(os.path.dirname(__file__), "settings.json")
BlacklistFile = os.path.join(os.path.dirname(__file__), "blacklist.json")
RefreshTokenFile = os.path.join(os.path.dirname(__file__), "tokens.json")
ReadMe = os.path.join(os.path.dirname(__file__), "README.txt")
EventReceiver = None
ThreadQueue = []
CurrentThread = None
Blacklist = []
TokenExpiration = None
LastTokenCheck = None # Used to make sure the bot doesn't spam trying to reconnect if there's a problem
RefreshToken = None
AccessToken = None
UserID = None

InvalidRefreshToken = False

#---------------------------------------
# Classes
#---------------------------------------
class Settings(object):
    def __init__(self, SettingsFile=None):
        if SettingsFile and os.path.isfile(SettingsFile):
            with codecs.open(SettingsFile, encoding="utf-8-sig", mode="r") as f:
                self.__dict__ = json.load(f, encoding="utf-8")
        else:
            self.EnableDebug = False
            self.TwitchRewardName = ""
            self.TwitchOAuthToken = ""
            self.BlacklistDuration = 3600
            self.EnableRedeemMessage = False
            self.RedeemMessage = "[username] has decreed that [word] shall not be used for [hours] hours!"
            self.EnableExpirationMessage = False
            self.ExpirationMessage = "[word] is now unlocked!"
            self.EnableTriggerMessage = False
            self.TriggerMessage = "[username] Said: [msg]"
            self.CensorPhrase = "[REDACTED]"

    def ReloadSettings(self, data):
        self.__dict__ = json.loads(data, encoding='utf-8-sig')

    def SaveSettings(self, settingsFile):
        try:
            with codecs.open(settingsFile, encoding='utf-8-sig', mode='w+') as f:
                json.dump(self.__dict__, f, encoding='utf-8-sig')
            with codecs.open(settingsFile.replace("json", "js"), encoding='utf-8-sig', mode='w+') as f:
                f.write("var settings = {0};".format(json.dumps(self.__dict__, encoding='utf-8-sig')))
        except ValueError:
            Parent.Log(ScriptName, "Failed to save settings to file.")


def ReloadSettings(jsonData):
    if ScriptSettings.EnableDebug:
        Parent.Log(ScriptName, "Saving settings.")

    try:
        ScriptSettings.__dict__ = json.loads(jsonData)
        ScriptSettings.Save(SettingsFile)

        RefreshTokens()
        if InvalidRefreshToken is False:
            if UserID is None:
                GetUserID()
            StopEventReceiver()
            StartEventReceiver()

        if ScriptSettings.EnableDebug:
            Parent.Log(ScriptName, "Settings saved successfully")
    except Exception as e:
        if ScriptSettings.EnableDebug:
            Parent.Log(ScriptName, str(e))
    return

#---------------------------
#   [Required] Initialize Data (Only called on load)
#---------------------------
def Init():
    global ScriptSettings
    ScriptSettings = Settings(SettingsFile)
    ScriptSettings.SaveSettings(SettingsFile)

    global Blacklist
    if os.path.isfile(BlacklistFile):
        with open(BlacklistFile) as f:
            content = f.readlines()
        for item in content:
            data = item.split(",")
            word = data[0]
            time = datetime.datetime.strptime(data[1], "%Y-%m-%d %H:%M:%S.%f")
            Blacklist.append((word, time))

    global RefreshToken
    global AccessToken
    global TokenExpiration
    if os.path.isfile(RefreshTokenFile):
        with open(RefreshTokenFile) as f:
            content = f.readlines()
        if len(content) > 0:
            data = json.loads(content[0])
            RefreshToken = data["refresh_token"]
            AccessToken = data["access_token"]
            TokenExpiration = datetime.datetime.strptime(data["expiration"], "%Y-%m-%d %H:%M:%S.%f")

    return

#---------------------------
#   [Required] Execute Data / Process messages
#---------------------------
def Execute(data):

    global Blacklist
    updatedList = []
    changed = False
    for item in Blacklist:
        if item[1] < datetime.datetime.now():
            if ScriptSettings.EnableExpirationMessage:
                Parent.SendStreamMessage(ScriptSettings.ExpirationMessage.replace("[word]", item[0]))
            changed = True
        else:
            updatedList.append(item)

    if changed:
        if ScriptSettings.EnableDebug:
            Parent.Log(ScriptName, "Blacklist changed.")
        Blacklist = updatedList
        SaveBlacklist()

    searchRegex = "\\b("
    for item in Blacklist:
            searchRegex += re.escape(item[0]) + "|"
    if searchRegex == "\\b(":
        return
    searchRegex = searchRegex[:-1] + ")\\b"

    if data.IsChatMessage() and data.IsFromTwitch():
        message = data.Message
        if ScriptSettings.EnableDebug:
            Parent.Log(ScriptName, "Regex search string: " + searchRegex)
            Parent.Log(ScriptName, data.RawData)
        matches = re.findall(searchRegex, message, re.IGNORECASE)

        if len(matches) == 0:
            if ScriptSettings.EnableDebug:
                Parent.Log(ScriptName, "No match found in message.")
            return 

        id = re.search(";id=([^,;]+);", data.RawData)

        if id is None:
            if ScriptSettings.EnableDebug:
                Parent.Log(ScriptName, "No id found in message.")
            return

        for item in matches:
            message = message.replace(item, ScriptSettings.CensorPhrase)

        if ScriptSettings.EnableDebug:
            Parent.Log(ScriptName, "Ids Found: " + id.group(1) + "Match Count: " + str(len(matches)))

        Parent.SendStreamMessage("/delete " + id.group(1))
        if ScriptSettings.EnableTriggerMessage:
            Parent.SendStreamMessage(ScriptSettings.TriggerMessage.replace("[username]", data.UserName).replace("[msg]", message))

    return

#---------------------------
#   [Required] Tick method (Gets called during every iteration even when there is no incoming data)
#---------------------------
def Tick():
    if (EventReceiver is None or TokenExpiration < datetime.datetime.now()) and LastTokenCheck + datetime.timedelta(seconds=60) < datetime.datetime.now(): 
        RefreshTokens();
        if InvalidRefreshToken is False:
            if UserID is None:
                GetUserID()
            StopEventReceiver()
            StartEventReceiver()
        return

    global CurrentThread
    if CurrentThread and CurrentThread.isAlive() == False:
        CurrentThread = None

    if CurrentThread == None and len(ThreadQueue) > 0:
        if ScriptSettings.EnableDebug:
            Parent.Log(ScriptName, "Starting new thread.")
        CurrentThread = ThreadQueue.pop(0)
        CurrentThread.start()
        
    return

#---------------------------
#   [Optional] Parse method (Allows you to create your own custom $parameters) 
#---------------------------
def Parse(parseString, userid, username, targetid, targetname, message):
    return parseString

#---------------------------
#   [Optional] Unload (Called when a user reloads their scripts or closes the bot / cleanup stuff)
#---------------------------
def Unload():
    SaveBlacklist()
    StopEventReceiver()
    return

#---------------------------
#   [Optional] ScriptToggled (Notifies you when a user disables your script or enables it)
#---------------------------
def ScriptToggled(state):
    if state:
        if EventReceiver is None:
            RefreshTokens()
            if InvalidRefreshToken is False:
                if UserID is None:
                    GetUserID()
                StartEventReceiver()
    else:
        SaveBlacklist()
        StopEventReceiver()

    return

#---------------------------
#   StartEventReceiver (Start twitch pubsub event receiver)
#---------------------------
def StartEventReceiver():
    if ScriptSettings.EnableDebug:
        Parent.Log(ScriptName, "Starting receiver")

    global EventReceiver
    EventReceiver = TwitchPubSub()
    EventReceiver.OnPubSubServiceConnected += EventReceiverConnected
    EventReceiver.OnRewardRedeemed += EventReceiverRewardRedeemed

    EventReceiver.Connect()

#---------------------------
#   StopEventReceiver (Stop twitch pubsub event receiver)
#---------------------------
def StopEventReceiver():
    global EventReceiver
    try:
        if EventReceiver:
            EventReceiver.Disconnect()
            if ScriptSettings.EnableDebug:
                Parent.Log(ScriptName, "Event receiver disconnected")
        EventReceiver = None

    except:
        if ScriptSettings.EnableDebug:
            Parent.Log(ScriptName, "Event receiver already disconnected")

#---------------------------
#   EventReceiverConnected (Twitch pubsub event callback for on connected event. Needs a valid UserID and AccessToken to function properly.)
#---------------------------
def EventReceiverConnected(sender, e):
    if ScriptSettings.EnableDebug:
        Parent.Log(ScriptName, "Event receiver connected, sending topics for channel id: " + str(UserID))

    EventReceiver.ListenToRewards(UserID)
    EventReceiver.SendTopics(AccessToken)
    return

#---------------------------
#   EventReceiverRewardRedeemed (Twitch pubsub event callback for a detected redeemed channel point reward.)
#---------------------------
def EventReceiverRewardRedeemed(sender, e):
    if ScriptSettings.EnableDebug:
        Parent.Log(ScriptName, "Event triggered: " + e.Message)
    if e.RewardTitle == ScriptSettings.TwitchRewardName:
        ThreadQueue.append(threading.Thread(target=RewardRedeemedWorker,args=(e.DisplayName, e.Message, ScriptSettings.BlacklistDuration)))
    return

#---------------------------
#   RewardRedeemedWorker (Worker function to be spun off into its own thread to complete without blocking the rest of script execution.)
#---------------------------
def RewardRedeemedWorker(username, word, duration):
    global Blacklist
    item = (word.strip(), datetime.datetime.now() + datetime.timedelta(0, duration))
    if ScriptSettings.EnableDebug:
        Parent.Log(ScriptName, str(item))
    Blacklist.append(item)
    SaveBlacklist()
    if ScriptSettings.EnableRedeemMessage:
        message = ScriptSettings.RedeemMessage.replace("[username]", username)
        message = message.replace("[word]", word)
        message = message.replace("[seconds]", str(duration))
        message = message.replace("[minutes]", str(math.trunc(duration/60)))
        message = message.replace("[hours]", str(math.trunc(duration/3600)))
        message = message.replace("[days]", str(math.trunc(duration/86400)))
        Parent.SendStreamMessage(message)

#---------------------------
#   RefreshTokens (Called when a new access token needs to be retrieved.)
#---------------------------
def RefreshTokens():
    global RefreshToken
    global AccessToken
    global TokenExpiration
    global LastTokenCheck

    result = None

    try:
        if RefreshToken:
            content = {
	            "grant_type": "refresh_token",
	            "refresh_token": str(RefreshToken)
            }

            result = json.loads(json.loads(Parent.PostRequest("https://api.et-twitch-auth.com/",{}, content, True))["response"])
            if ScriptSettings.EnableDebug:
                Parent.Log(ScriptName, str(content))
        else:
            if ScriptSettings.TwitchAuthCode == "":
                LastTokenCheck = datetime.datetime.now()
                TokenExpiration = datetime.datetime.now()
                Parent.Log(ScriptName, "Access code cannot be retrieved please enter a valid authorization code.")
                InvalidRefreshToken = True
                return

            content = {
                'grant_type': 'authorization_code',
                'code': ScriptSettings.TwitchAuthCode
            }

            result = json.loads(json.loads(Parent.PostRequest("https://api.et-twitch-auth.com/",{}, content, True))["response"])
            if ScriptSettings.EnableDebug:
                Parent.Log(ScriptName, str(content))

        if ScriptSettings.EnableDebug:
            Parent.Log(ScriptName, str(result))

        RefreshToken = result["refresh_token"]
        AccessToken = result["access_token"]
        TokenExpiration = datetime.datetime.now() + datetime.timedelta(seconds=int(result["expires_in"]) - 300)

        LastTokenCheck = datetime.datetime.now()
        SaveTokens()
    except Exception as e:
        LastTokenCheck = datetime.datetime.now()
        TokenExpiration = datetime.datetime.now()
        if ScriptSettings.EnableDebug:
            Parent.Log(ScriptName, "Exception: " + str(e.message))
        InvalidRefreshToken = True

#---------------------------
#   GetUserID (Calls twitch's api with current channel user name to get the user id and sets global UserID variable.)
#---------------------------
def GetUserID():
    global UserID
    headers = { 
        "Client-ID": "icyqwwpy744ugu5x4ymyt6jqrnpxso",
        "Authorization": "Bearer " + AccessToken
    }
    result = json.loads(Parent.GetRequest("https://api.twitch.tv/helix/users?login=" + Parent.GetChannelName(), headers))
    if ScriptSettings.EnableDebug:
        Parent.Log(ScriptName, "headers: " + str(headers))
        Parent.Log(ScriptName, "result: " + str(result))
    user = json.loads(result["response"])
    UserID = user["data"][0]["id"]

#---------------------------
#   SaveBlacklist (Saves list of blacklisted words to file for use on script restart and reload)
#---------------------------
def SaveBlacklist():
    with open(BlacklistFile, 'w') as f:
        for item in Blacklist:
            f.write(str(item[0]) + "," + str(item[1]) + "\n")

#---------------------------
#   SaveTokens (Saves tokens and expiration time to a json file in script bin for use on script restart and reload.)
#---------------------------
def SaveTokens():
    data = {
        "refresh_token": RefreshToken,
        "access_token": AccessToken,
        "expiration": str(TokenExpiration)
    }

    with open(RefreshTokenFile, 'w') as f:
        f.write(json.dumps(data))

#---------------------------
#   OpenReadme (Attached to settings button to open the readme file in the script bin.)
#---------------------------
def OpenReadme():
    os.startfile(ReadMe)

#---------------------------
#   GetToken (Attached to settings button to open a page in browser to get an authorization code.)
#---------------------------
def GetToken():
	os.startfile("https://id.twitch.tv/oauth2/authorize?response_type=code&client_id=icyqwwpy744ugu5x4ymyt6jqrnpxso&redirect_uri=https://et-twitch-auth.com/&scope=channel:read:redemptions&force_verify=true")

#---------------------------
#   DeleteSavedTokens (Attached to settings button to allow user to easily delete the tokens.json file and clear out RefreshToken currently in memory so that a new authorization code can be entered and used.)
#---------------------------
def DeleteSavedTokens():
    global RefreshToken
    if os.path.exists(RefreshTokenFile):
        os.remove(RefreshTokenFile)
    RefreshToken = None