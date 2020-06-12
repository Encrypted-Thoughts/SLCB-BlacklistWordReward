# -*- coding: utf-8 -*-

#---------------------------
#   Import Libraries
#---------------------------
import clr, codecs, json, os, re, sys, threading, datetime, math

clr.AddReference("IronPython.Modules.dll")
clr.AddReferenceToFileAndPath(os.path.join(os.path.dirname(os.path.realpath(__file__)) + "\References", "TwitchLib.PubSub.dll"))
from TwitchLib.PubSub import TwitchPubSub

#---------------------------
#   [Required] Script Information
#---------------------------
ScriptName = "Blacklist Word Reward"
Website = "https://www.twitch.tv/EncryptedThoughts"
Description = "Script to allow users to blacklist a word as a channel point reward."
Creator = "EncryptedThoughts"
Version = "1.0.0.0"

#---------------------------
#   Define Global Variables
#---------------------------
SettingsFile = os.path.join(os.path.dirname(__file__), "settings.json")
BlacklistFile = os.path.join(os.path.dirname(__file__), "blacklist.json")
ReadMe = os.path.join(os.path.dirname(__file__), "README.txt")
EventReceiver = None
ThreadQueue = []
CurrentThread = None
Blacklist = []

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
    # Execute json reloading here
    if ScriptSettings.EnableDebug:
        Parent.Log(ScriptName, "Saving settings.")

    ScriptSettings.ReloadSettings(jsonData)

    try:
        Stop()
        Start()
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

    return

def Start():
    if ScriptSettings.EnableDebug:
        Parent.Log(ScriptName, "Starting receiver");

    global EventReceiver
    EventReceiver = TwitchPubSub()
    EventReceiver.OnPubSubServiceConnected += EventReceiverConnected
    EventReceiver.OnRewardRedeemed += EventReceiverRewardRedeemed    

    EventReceiver.Connect()

def Stop():
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

def EventReceiverConnected(sender, e):

    if ScriptSettings.EnableDebug:
        Parent.Log(ScriptName, "Event receiver connecting")

    #get channel id for username
    headers = { 
        "Client-ID": "icyqwwpy744ugu5x4ymyt6jqrnpxso",
        "Authorization": "Bearer " + ScriptSettings.TwitchOAuthToken[6:] 
    }
    result = json.loads(Parent.GetRequest("https://api.twitch.tv/helix/users?login=" + Parent.GetChannelName(), headers))
    if ScriptSettings.EnableDebug:
        Parent.Log(ScriptName, "headers: " + str(headers))
        Parent.Log(ScriptName, "result: " + str(result))
    user = json.loads(result["response"])
    id = user["data"][0]["id"]

    if ScriptSettings.EnableDebug:
        Parent.Log(ScriptName, "Event receiver connected, sending topics for channel id: " + id)

    EventReceiver.ListenToRewards(id)
    EventReceiver.SendTopics(ScriptSettings.TwitchOAuthToken)
    return

def EventReceiverRewardRedeemed(sender, e):
    if ScriptSettings.EnableDebug:
        Parent.Log(ScriptName, "Event triggered: " + e.Message)
    if e.RewardTitle == ScriptSettings.TwitchRewardName:
        ThreadQueue.append(threading.Thread(target=RewardRedeemedWorker,args=(e.DisplayName, e.Message, ScriptSettings.BlacklistDuration)))
    return

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

def SaveBlacklist():
    with open(BlacklistFile, 'w') as f:
        for item in Blacklist:
            f.write(str(item[0]) + "," + str(item[1]) + "\n")

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

    ## Init the Channel Points Event Receiver
    global EventReceiver
    if EventReceiver is None:
        Start()

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
    # Disconnect EventReceiver cleanly
    SaveBlacklist()
    Stop()
    return

#---------------------------
#   [Optional] ScriptToggled (Notifies you when a user disables your script or enables it)
#---------------------------
def ScriptToggled(state):
    if state:
        if EventReceiver is None:
            Start()
    else:
        SaveBlacklist()
        Stop()

    return

def OpenReadme():
    os.startfile(ReadMe)

def GetToken():
	os.startfile("https://id.twitch.tv/oauth2/authorize?response_type=token&client_id=icyqwwpy744ugu5x4ymyt6jqrnpxso&redirect_uri=https://twitchapps.com/tmi/&scope=channel:read:redemptions&force_verify=true")