# -*- coding: utf-8 -*-

#---------------------------
#   Import Libraries
#---------------------------
import codecs, json, os, re, sys, datetime, math

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
            self.BlacklistCommand = "!blacklist"
            self.BlacklistCost = 500
            self.BlacklistDuration = 3600
            self.EnableRedeemMessage = False
            self.RedeemMessage = "[username] has decreed that [word] shall not be used for [hours] hours!"
            self.EnableExpirationMessage = False
            self.ExpirationMessage = "[word] is now unlocked!"
            self.EnableTriggerMessage = False
            self.TriggerMessage = "[username] Said: [msg]"
            self.CensorPhrase = "[REDACTED]"

    def Reload(self, jsondata):
        self.__dict__ = json.loads(jsondata, encoding="utf-8")

    def Save(self, SettingsFile):
        try:
            with codecs.open(SettingsFile, encoding="utf-8-sig", mode="w+") as f:
                json.dump(self.__dict__, f, encoding="utf-8")
            with codecs.open(SettingsFile.replace("json", "js"), encoding="utf-8-sig", mode="w+") as f:
                f.write("var settings = {0};".format(json.dumps(self.__dict__, encoding='utf-8')))
        except:
            Parent.Log(ScriptName, "Failed to save settings to file.")
        return

def ReloadSettings(jsonData):
    ScriptSettings.Reload(jsonData)

#---------------------------
#   [Required] Initialize Data (Only called on load)
#---------------------------
def Init():
    global ScriptSettings
    ScriptSettings = Settings(SettingsFile)
    ScriptSettings.Save(SettingsFile)

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

    if data.IsChatMessage() and data.IsFromTwitch():
        if data.GetParam(0).lower() == ScriptSettings.BlacklistCommand:
            if Parent.GetPoints(data.User) >= ScriptSettings.BlacklistCost and data.GetParam(1) != None and data.GetParam(1) != "":
                RewardRedeemedWorker(data.UserName, data.Message.replace(data.GetParam(0), ""), ScriptSettings.BlacklistDuration)
                Parent.RemovePoints(data.User,data.UserName,ScriptSettings.BlacklistCost)
            else:
                Parent.SendStreamMessage("Either you don't have " + str(ScriptSettings.BlacklistCost) + " " + str(Parent.GetPoints(data.User)) + " points or you didn't enter a valid entry to blacklist.")

        else:
            searchRegex = "\\b("
            for item in Blacklist:
                    searchRegex += re.escape(item[0]) + "|"
            if searchRegex == "\\b(":
                return
            searchRegex = searchRegex[:-1] + ")\\b"

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
#   [Required] Tick method (Gets called during every iteration even when there is no incoming data)
#---------------------------
def Tick():
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
    return

#---------------------------
#   [Optional] ScriptToggled (Notifies you when a user disables your script or enables it)
#---------------------------
def ScriptToggled(state):
    SaveBlacklist()
    return

def openreadme():
    os.startfile(ReadMe)