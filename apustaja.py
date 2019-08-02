# -*- coding: utf-8 -*-
import os, io, sys, time, ssl, random, datetime, calendar, logging, re, atexit
import telepot, gtts, urllib.request, holidays, multiprocessing, pytz, sqlite3

from sqlite3 import OperationalError
from mtranslate import translate
from pydub import AudioSegment
from gtts import gTTS
from datetime import date
from uptime import uptime
from urllib.request import urlopen
from bs4 import BeautifulSoup
from telepot.loop import MessageLoop
from multiprocessing import Pool, Process
from urllib.parse import quote

try: # get some speedup for json decoding with ujson
	import ujson as json
except ImportError:
	import json


def exitHandler():
	if debugLog is True:
		logging.info('😴 Program closing')


def handle(msg):
	try:
		content_type, chat_type, chat = telepot.glance(msg, flavor="chat")
	except KeyError:
		if debugLog is True:
			# why is this here?
			logging.info(f'Failure in glance: {msg}')
		return

	chatDir = 'data/chats/' + str(chat)
	timestamp = time.time()
	today = datetime.datetime.today()

	# group upgraded to a supergroup; migrate data
	if 'migrate_to_chat_id' in msg:
		oldID = chat
		newID = msg['migrate_to_chat_id']

		if debugLog is True:
			logging.info(f'⚠️ Group {oldID} migrated to {newID}; starting data migration.')

		# do the migration simply by renaming the chat's directory
		oldChatDir = 'data/chats/' + str(oldID)
		newChatDir = 'data/chats/' + str(newID)
		os.rename(oldChatDir, newChatDir)

		# migrate chat stats to new chat
		migrateStats(oldID, newID)

		if debugLog is True:
			logging.info('✅ Chat data migration complete!')

	# bot removed from chat; delete all chat data permanently
	if 'left_chat_member' in msg and msg['left_chat_member']['id'] == botID:
		# first remove all files in the folder
		fileList = []
		try:
			for file in os.listdir(chatDir):
				fileList.append(file)
				os.remove(os.path.join(chatDir, file))

			os.rmdir(chatDir)

		except FileNotFoundError:
			pass

		if debugLog is True:
			logging.info(f'⚠️ Bot removed from chat {chat}; data purged.')

	# detect if bot added to a new chat
	if 'new_chat_members' in msg or 'group_chat_created' in msg:
		if 'new_chat_member' in msg:
			try:
				if botID in msg['new_chat_member']['id']:
					pass
				else:
					return
			
			except TypeError:
				if msg['new_chat_member']['id'] == botID:
					pass
				else:
					return
		elif 'group_chat_created' in msg:
			if msg['group_chat_created'] is True:
				pass
			else:
				return

		header = f'🤖 *Apustaja versio {versionumero}*\n'
		mid = f'Hei, olen Apustaja! Alla on listattuna kasa komentoja joita voit käyttää. '
		mid += 'Tarkempaa tietoa komennoista saat kokeilemalla niitä tai lukemalla tarkat ohjeet Githubista!\n\n'

		cmdMarkov = f'*/markov:* Muodosta satunnaisgeneroituja viestejä (Botnet? Lue Github!)\n'
		cmdUM = f'*/um:* Uhka vai mahdollisuus?\n'
		cmdSaa = f'*/saa:* Kertoo tämänhetkisen sään. Oletuskaupungin voit asettaa komennolla `[/settings saa defaultCity]`\n'
		cmdRoll = f'*/roll:* Heitä kolikkoa, gettaa tuplat tai pyöritä noppaa\n'
		cmdReplace = f'*/s:* Korvaa jonkun muun viestissä tekstiä toisella tekstillä\n'
		cmdTts = f'*/tts:* Muuta tekstiä ääneksi esimerkiksi vastaamalla viestiin tai ajamalla `[/tts /markov]`\n'
		cmdSett = f'*/settings:* Muuta Apustajan ryhmäkohtaisia asetuksia `[admineille]`\n'
		cmdInfo = f'*/info:* Tilastoja, faktoja ja analyysejä.\n\n'
		gitInfo = f'🤙 *Hostaa itse, forkkaa tai ihmettele spagettikoodia!*\nhttps://github.com/apustaja/apustaja'

		replymsg = header+mid+cmdMarkov+cmdUM+cmdSaa+cmdRoll+cmdReplace+cmdTts+cmdSett+cmdInfo+gitInfo
		bot.sendMessage(chat, replymsg, parse_mode='Markdown')

		if debugLog is True:
			logging.info('🌟 Bot added to a new chat!')

		# create the folders for the chat
		if not os.path.isdir(chatDir):
			if not os.path.isdir('data/chats'):
				if not os.path.isdir('data'):
					os.mkdir('data')

				os.mkdir('data/chats')

			os.mkdir(chatDir)
	
	if 'text' in msg:
		commandSplit = msg['text'].strip().split(" ")

	# store message if it doesn't _start_ as a bot command. We don't care if it has a (probably unintended) command in it somewhere else
	if content_type == 'text' and commandSplit[0][0] != '/':
		if not os.path.isfile(chatDir + 'chainStore.db'):
			createDatabase(msg)

		# update database
		updateDatabase(parseMessage(msg), msg)

		# update stats database
		updateStats(msg, 'message')
	
	# sees a valid command
	elif content_type == 'text':
		if commandSplit[0].lower() in validCommands or commandSplit[0] in validCommandsAlt:
			# command we saw
			command = commandSplit[0].lower()
			
			# store statistics if command is valid (also ignores /info)
			if command != validCommands[2] and command != validCommandsAlt[2]:
				updateStats(msg, 'command')

			# if /markov
			if command == validCommands[0].lower() or command == validCommandsAlt[0]:
				if timerHandle(msg,command) is False:
					return

				bot.sendChatAction(chat, action='typing')
				markov(msg, commandSplit, chat)
				return
			
			# if /s
			elif command == validCommands[1] or command == validCommandsAlt[1]:
				if timerHandle(msg,command) is False:
					return

				bot.sendChatAction(chat, action='typing')
				replace(msg)
				return

			# /info 
			elif command == validCommands[2] or command == validCommandsAlt[2]:
				if timerHandle(msg,command) is False:
					return

				bot.sendChatAction(chat, action='typing')

				replymsg = info(msg)
				bot.sendMessage(msg['chat']['id'], replymsg, parse_mode="Markdown")
				return

			# /saa
			elif command == validCommands[3] or command == validCommandsAlt[3]:
				if timerHandle(msg,command) is False:
					return

				bot.sendChatAction(chat, action='typing')
				weatherReply = saa(msg,0)
				bot.sendMessage(msg['chat']['id'], weatherReply, parse_mode="Markdown")
				return

			# /tuet
			elif command == validCommands[4] or command == validCommandsAlt[4]:
				if timerHandle(msg,command) is False:
					return

				bot.sendChatAction(chat, action='typing')
				tuet(msg)
				return

			# /um
			elif command == validCommands[5] or command == validCommandsAlt[5]:
				if timerHandle(msg,command) is False:
					return

				bot.sendChatAction(chat, action='typing')

				respstr = um()
				commandSplit = msg['text'].lower().strip().split(" ")

				# reply to a message, with only /um and no extra arguments; reply to replied message
				if 'reply_to_message' in msg and len(commandSplit) is 1:
					bot.sendMessage(chat, respstr, reply_to_message_id=msg['reply_to_message']['message_id'])
				
				# reply to a message, but there are extra arguments; reply to sender
				elif 'reply_to_message' in msg and len(commandSplit) > 1:
					bot.sendMessage(chat, respstr, reply_to_message_id=msg['message_id'])
				
				# not a reply to a message. If no args, just generate text.
				elif not 'reply_to_message' in msg: 
					if len(commandSplit) > 1:
						bot.sendMessage(chat, respstr, reply_to_message_id=msg['message_id'])
					else:
						bot.sendMessage(chat, respstr)

				return

			# /settings
			elif command == validCommands[6] or command == validCommandsAlt[6]:
				bot.sendChatAction(chat, action='typing')
				settings(msg)

				return

			# /tts
			elif command == validCommands[7] or command == validCommandsAlt[7]:
				if timerHandle(msg,command) is False:
					return

				if len(commandSplit) > 1:
					bot.sendChatAction(chat, action='record_audio')
					tts(msg,'text')
				else:
					# no text; check if it was a reply to a message
					if 'reply_to_message' in msg:
						if 'text' in msg['reply_to_message']:
							if len(msg['reply_to_message']['text']) is not 0:
								bot.sendChatAction(chat, action='record_audio')
								tts(msg,'reply')

						elif 'caption' in msg['reply_to_message']:
							if len(msg['reply_to_message']['caption']) is not 0:
								bot.sendChatAction(chat, action='record_audio')
								
								# modify message's content
								captionText = msg['reply_to_message']['caption']
								msg['reply_to_message']['text'] = captionText

								tts(msg,'reply')
					else:
						bot.sendChatAction(chat, action='typing')
						bot.sendMessage(chat, '*Käyttö:* /tts [teksti], /tts [/markov] tai /tts vastauksena viestiin.', reply_to_message_id=msg['message_id'], parse_mode='Markdown')

				return

			# /webcam
			elif command == validCommands[8] or command == validCommandsAlt[8]:
				if timerHandle(msg,command) is False:
					return

				webcam(msg)
				return

			# /roll
			elif command == validCommands[9] or command == validCommandsAlt[9]:
				if timerHandle(msg,command) is False:
					return

				bot.sendChatAction(chat, action='typing')
				roll(msg)
				return

			# /start
			elif command == validCommands[10] or command == validCommandsAlt[10] or command == validCommands[11] or command == validCommandsAlt[11]:
				# construct info message
				header = f'🤖 *Apustaja versio {versionumero}*\n'
				mid = f'Hei, olen Apustaja! Alla on listattuna kasa komentoja joita voit käyttää. '
				mid += 'Tarkempaa tietoa komennoista saat kokeilemalla niitä tai lukemalla tarkat ohjeet Githubista!\n\n'

				cmdMarkov = f'*/markov:* Muodosta satunnaisgeneroituja viestejä (Botnet? Lue Github!)\n'
				cmdUM = f'*/um:* Uhka vai mahdollisuus?\n'
				cmdSaa = f'*/saa:* Kertoo tämänhetkisen sään. Oletuskaupungin voit asettaa komennolla `[/settings saa defaultCity]`\n'
				cmdRoll = f'*/roll:* Heitä kolikkoa, gettaa tuplat tai pyöritä noppaa\n'
				cmdReplace = f'*/s:* Korvaa jonkun muun viestissä tekstiä toisella tekstillä\n'
				cmdTts = f'*/tts:* Muuta tekstiä ääneksi esimerkiksi vastaamalla viestiin tai ajamalla `[/tts /markov]`\n'
				cmdSett = f'*/settings:* Muuta Apustajan ryhmäkohtaisia asetuksia `[admineille]`\n'
				cmdInfo = f'*/info:* Tilastoja, faktoja ja analyysejä.\n'
				gitInfo = f'\n🤙 *Hostaa itse, forkkaa tai ihmettele spagettikoodia!*\nhttps://github.com/apustaja/apustaja'

				replymsg = header+mid+cmdMarkov+cmdUM+cmdSaa+cmdRoll+cmdReplace+cmdTts+cmdSett+cmdInfo+gitInfo
				bot.sendMessage(chat, replymsg, parse_mode='Markdown')

				return

		else:
			return


def migrateStats(oldID, newID):
	# open db connection
	statsConn = sqlite3.connect('data/stats.db')
	statsCursor = statsConn.cursor()

	try: # check if stats db exists
		statsCursor.execute("CREATE TABLE stats (chatID INTEGER, msgCount INTEGER, cmdCount INTEGER)")
	except sqlite3.OperationalError:
		pass # database exists, pass	

	try: # if there are any old stats, simply insert a new chatID into the db, replacing the old one
		statsCursor.execute("UPDATE stats SET chatID = ? WHERE chatID = ?", (newID, oldID))	
	except: # if no stats for chat (should never happen, but let's handle it anyway), create some with the new ID
		statsCursor.execute("INSERT INTO stats (chatID, msgCount, cmdCount) VALUES (?, ?, ?)", (newID, 0, 0))

	return


def updateStats(msg, type):
	content_type, chat_type, chat = telepot.glance(msg, flavor='chat')
	
	# open db connection
	statsConn = sqlite3.connect('data/stats.db')
	statsCursor = statsConn.cursor()

	try: # check if stats db exists
		statsCursor.execute("CREATE TABLE stats (chatID INTEGER, msgCount INTEGER, cmdCount INTEGER, PRIMARY KEY (chatID))")
	except sqlite3.OperationalError:
		pass

	if type == 'message':
		try:
			statsCursor.execute("INSERT INTO stats (chatID, msgCount, cmdCount) VALUES (?, ?, ?)", (chat, 1, 0))
		except:
			statsCursor.execute("UPDATE stats SET msgCount = msgCount + 1 WHERE chatID = ?", (chat,))


	elif type == 'command':
		try:
			statsCursor.execute("INSERT INTO stats (chatID, msgCount, cmdCount) VALUES (?, ?, ?)", (chat, 0, 1))
		except:
			statsCursor.execute("UPDATE stats SET cmdCount = cmdCount + 1 WHERE chatID = ?", (chat,))

	statsConn.commit()
	statsConn.close()
	return


def settings(msg):
	content_type, chat_type, chat = telepot.glance(msg, flavor="chat")

	# check if caller is an admin
	sender = bot.getChatMember(chat, msg['from']['id'])
	chatType = bot.getChat(chat)['type']

	if chatType == 'private' or sender['status'] == 'creator' or sender['status'] == 'administrator':
		None
	else:
		bot.sendMessage(chat, 'Komentoa voi kutsua vain ryhmän admin.',reply_to_message_id=msg['message_id'])
		return

	# /settings [arg1] [arg2] [arg3]
	validArg1 = ['timer', 'status', 'saa', 'tts']

	# start off by generating setting file for chat, if it doesn't exist already
	if not os.path.isfile("data/chats/" + str(chat) + "/settings.json"):
		if not os.path.isdir("data/chats/" + str(chat)):
			os.mkdir("data/chats/" + str(chat))

		with open("data/chats/" + str(chat) +  "/settings.json", 'w') as jsonData:
			settingMap = {} # empty .json file
			
			# generate fields
			settingMap['commandTimers'] = {}
			for command in validCommands:
				command = command.replace('/','')
				settingMap['commandTimers'][command] = 0.75

			settingMap['saa'] = {}
			settingMap['saa']['defaultCity'] = 'Otaniemi'

			json.dump(settingMap, jsonData, indent=4, sort_keys=True)

	# parse message
	commandSplit = msg['text'].lower().strip().split(" ") # [0] is the command itself

	# only /settings called; print current settings
	if len(commandSplit) is 1:
		header = '*Apustajan ryhmä- ja komentokohtaiset asetukset*\n'
		mid = '*Huom:* komennon kutsujan tulee olla ryhmän admin tai perustaja.'
		low = '*Lisäargumentit:* timer, status, saa, tts\n'
		replymsg = header + low + mid
		bot.sendMessage(chat,replymsg,parse_mode="Markdown")
		return

	# there are some actual arguments
	else:
		arg1 = commandSplit[1]

		# if the argument is valid
		if arg1 in validArg1:
			# timer
			if validArg1[0] == arg1:
				if len(commandSplit) is 4:
					command = '/' + commandSplit[2]
					if command in validCommands and commandSplit[2] != 'settings':
						timerCommand = commandSplit[2]
						timer = commandSplit[3]

						with open("data/chats/" + str(chat) +  "/settings.json") as jsonData:
							settingMap = json.load(jsonData)

						try:
							float(timer)
							with open("data/chats/" + str(chat) +  "/settings.json", 'w') as jsonData:
								settingMap['commandTimers'][timerCommand] = timer # store as string
								json.dump(settingMap, jsonData, indent=4, sort_keys=True)
								bot.sendMessage(chat,'✅ Asetus päivitetty onnistuneesti!',reply_to_message_id=msg['message_id'])
						
						except ValueError:
							bot.sendMessage(chat,'Annettu aika ei ole numero.',reply_to_message_id=msg['message_id'])
					
					elif commandSplit[2] == 'settings':
						bot.sendMessage(chat,'/settings komentoa ei voi aikarajoittaa!',reply_to_message_id=msg['message_id'])
				
				else:
					top = '*Rajoita tai estä komennon kutsuminen*\n'
					header = '*Argumentit:* timer _(rajoitettava komento) (aika sekunteina)_\n'
					mid = '*Esim:* /settings timer markov 60 (-1 estää komennon)'
					replymsg = top + header + mid
					bot.sendMessage(chat, replymsg, parse_mode="Markdown")
			
			# status			
			elif validArg1[1] == arg1:
				header = '*Apustajan asetuksien status*\n\n'
				header1 = '⏱ *Ajastimet*\n'
				ajastimet = ''

				try:
					with open("data/chats/" + str(chat) +  "/settings.json", 'r') as jsonData:
						settingMap = json.load(jsonData)
						for key, value in settingMap['commandTimers'].items():
							if float(value) < 0:
								ajastimet = ajastimet + '*{:s}* komento ei käytössä\n'.format(key)
							elif float(value) >= 0:
								if value is 1:
									ajastimet = ajastimet + '*{:s}* {:s} sekunti\n'.format(key,str(value))
								else:
									ajastimet = ajastimet + '*{:s}* {:s} sekuntia\n'.format(key,str(value))

					replyMsg = header + header1 + ajastimet
					bot.sendMessage(chat, replyMsg, parse_mode='Markdown')

				except FileNotFoundError:
					if not os.path.isdir("data/chats/" + str(chat)):
						os.mkdir("data/chats/" + str(chat))

					with open("data/chats/" + str(chat) +  "/settings.json", 'w') as jsonData:
						settingMap = {} # empty .json file
						
						# generate fields
						settingMap['commandTimers'] = {}
						for command in validCommands:
							command = command.replace('/','')
							settingMap['commandTimers'][command] = 0.75
						
						json.dump(settingMap, jsonData, indent=4, sort_keys=True)
						settings(msg) # call messages again to print the values now that the file exists
						return

			# saa
			elif validArg1[2] == arg1:
				# /settings saa defaultCity KAUPUNKI
				if len(commandSplit) >= 4:
					if commandSplit[2].lower() == 'defaultcity':
						words = commandSplit[3:]

						newDefault = ''
						m = 0
						for n in words:
							newDefault += n

							if m < len(words) - 1:
								newDefault += ' '

							m += 1

						with open("data/chats/" + str(chat) +  "/settings.json") as jsonData:
							settingMap = json.load(jsonData)

						try:
							settingMap['saa']['defaultCity'] = newDefault
							with open("data/chats/" + str(chat) +  "/settings.json", 'w') as jsonData:
								json.dump(settingMap, jsonData, indent=4, sort_keys=True)
						
						except KeyError:
							settingMap['saa'] = {}
							settingMap['saa']['defaultCity'] = newDefault

							with open("data/chats/" + str(chat) +  "/settings.json", 'w') as jsonData:
								json.dump(settingMap, jsonData, indent=4, sort_keys=True)

						bot.sendMessage(chat, '✅ Oletuskaupunki päivitetty onnistuneesti!')

				else:
					bot.sendMessage(chat, '🌤 Käyttö: /settings saa defaultCity KAPUNGIN NIMI\nEsimerkki: /settings saa defaultCity New York')

			# /tts
			elif validArg1[3] == arg1:
				# valid choices as a dictionary: validLanguages[short] = languageName
				validLanguages = gtts.lang.tts_langs()

				# /settings tts [arg] [val]
				if len(commandSplit) >= 4:
					if commandSplit[2].lower() == 'defaultlanguage':
						languageArg = commandSplit[3].capitalize()

						# check if language is in validLanguages
						if languageArg in validLanguages.values():
							for key, val in validLanguages.items():
								if val == languageArg:
									defaultLanguage = key
									if languageArg == 'English':
										defaultLanguage = 'en-us'

									break

						else:
							bot.sendMessage(chat,'Not a valid language!\nUsage example: /settings tts defaultLanguage French')
							return

						with open("data/chats/" + str(chat) +  "/settings.json") as jsonData:
							settingMap = json.load(jsonData)

							try:
								settingMap['tts']['defaultLanguage'] = defaultLanguage
								with open("data/chats/" + str(chat) +  "/settings.json", 'w') as jsonData:
									json.dump(settingMap, jsonData, indent=4, sort_keys=True)
							
							except KeyError:
								settingMap['tts'] = {}
								settingMap['tts']['defaultLanguage'] = defaultLanguage

								with open("data/chats/" + str(chat) +  "/settings.json", 'w') as jsonData:
									json.dump(settingMap, jsonData, indent=4, sort_keys=True)

							bot.sendMessage(chat, '✅ Oletuskieli päivitetty onnistuneesti!')

				else:
					bot.sendMessage(chat, '🌤 Käyttö: /settings tts defaultLanguage KIELI\nEsimerkki: /settings tts defaultLanguage English')


			else:
				bot.sendMessage(chat,'Ei kelpaava komento!')

	return


def unescapematch(matchobj):
	escapesequence = matchobj.group(0)
	digits = escapesequence[2:]
	ordinal = int(digits, 16)
	char = unichr(ordinal)
	return char


def timerHandle(msg,command):
	# remove the '/' command prefix
	command = command.strip('/')

	if '@' in command:
		command = command.split('@')
		command = command[0]

	content_type, chat_type, chat = telepot.glance(msg, flavor="chat")

	# get current time
	now_called = datetime.datetime.today() # now

	# check if settings.json exists
	if not os.path.isfile("data/chats/" + str(chat) + "/settings.json"):
		if not os.path.isdir("data/chats/" + str(chat)):
			os.mkdir("data/chats/" + str(chat))

		with open("data/chats/" + str(chat) +  "/settings.json", 'w') as jsonData:
			settingMap = {} # empty .json file
			
			# generate fields
			settingMap['commandTimers'] = {}
			for command in validCommands:
				command = command.replace('/','')
				settingMap['commandTimers'][command] = 1.0
			
			json.dump(settingMap, jsonData, indent=4, sort_keys=True)

	# load settings
	with open("data/chats/" + str(chat) +  "/settings.json", 'r') as jsonData:
		settingMap = json.load(jsonData)

	# load timer for command
	try:
		timer = float(settingMap['commandTimers'][command])
	
	except KeyError:
		with open("data/chats/" + str(chat) +  "/settings.json", 'w') as jsonData:
			settingMap = json.load(jsonData)
			settingMap['commandTimers'][command] = '2'
			json.dump(settingMap, jsonData, indent=4, sort_keys=True)

		timer = float(settingMap['commandTimers'][command])

	if timer == -1 or timer < -1:
		return False

	# load time the command was previously called
	if not os.path.isfile("data/chats/" + str(chat) + "/last.json"):
		with open("data/chats/" + str(chat) +  "/last.json", 'w') as jsonData:
			lastMap = {}
			lastMap[command] = '0'
			json.dump(lastMap, jsonData, indent=4, sort_keys=True)

	with open("data/chats/" + str(chat) +  "/last.json") as jsonData:
		lastMap = json.load(jsonData)

	try:
		last_called = lastMap[command]
	except KeyError:
		lastMap[command] = '0'
		last_called = lastMap[command]

	if last_called is '0': # never called; store now
		lastMap[command] = str(now_called) # stringify datetime object, store
		with open("data/chats/" + str(chat) +  "/last.json", 'w') as jsonData:
			json.dump(lastMap, jsonData, indent=4, sort_keys=True)
	else:
		last_called = datetime.datetime.strptime(last_called, "%Y-%m-%d %H:%M:%S.%f") # unstring datetime object
		time_since = abs(now_called - last_called)

		if time_since.seconds > timer:
			lastMap[command] = str(now_called) # stringify datetime object, store
			with open("data/chats/" + str(chat) +  "/last.json", 'w') as jsonData:
				json.dump(lastMap, jsonData, indent=4, sort_keys=True)
		else:
			return False

	return True


def createDatabase(msg):
	content_type, chat_type, chat = telepot.glance(msg, flavor='chat')
	chatDir = 'data/chats/' + str(chat)

	# create folder for chat
	if not os.path.isdir(chatDir):
		os.mkdir(chatDir)

		if debugLog is True:
			logging.info('🌟 New chat detected!')

	# Establish connection
	conn = sqlite3.connect(chatDir + '/' + 'chainStore.db')
	c = conn.cursor()

	try:
		c.execute("CREATE TABLE pairs (word1baseform TEXT, word1 TEXT, word2 TEXT, count INTEGER, PRIMARY KEY (word1, word2))")
		c.execute("CREATE INDEX baseform ON pairs (word1baseform, word2)")
	except sqlite3.OperationalError:
		pass

	conn.commit()
	conn.close()
	return


def parseMessage(msg):
	# slice our message into individual words and remove unix escape char fuckery
	sentence = msg['text'].strip()
	sentence = re.sub(r'(\\u[0-9A-Fa-f]{1,4})', unescapematch, sentence)
	sentence = sentence.replace('\r\n', ' ').replace('\n', ' ').replace('  ', ' ').split(" ")

	n = 0
	chainStore = {}
	for word in sentence:
		if n <= len(sentence) - 2 and word != '': # unless second last word, continue eg. 10 chars -> len is 10 -> index 0..9; if n is 8, stop
			if word == ' ':
				pass

			after = sentence[n + 1]

			# word not seen before
			if word not in chainStore:
				chainStore[word] = {after: 1}

			# word seen before
			else:
				if after in chainStore[word]:
					chainStore[word][after] = chainStore[word][after] + 1

				else:
					chainStore[word][after] = 1
			
			n += 1

		### new
		elif n == len(sentence) - 1 and word != '':
			after = ''

			# word not seen before
			if word not in chainStore:
				chainStore[word] = {after: 1}

			# word seen before
			else:
				if after in chainStore[word]:
					chainStore[word][after] = chainStore[word][after] + 1

				else:
					chainStore[word][after] = 1
			
			n += 1

		# this was here :^)
		elif len(sentence) is 1:
			# nothing :^(
			after = ''

			# word not seen before
			if word not in chainStore:
				chainStore[word] = {after: 1}

			# word seen before
			else:
				if after in chainStore[word]:
					chainStore[word][after] = chainStore[word][after] + 1

				else:
					chainStore[word][after] = 1

	return chainStore


def updateDatabase(chainStore, msg): 
	content_type, chat_type, chat = telepot.glance(msg, flavor='chat')
	chatDir = 'data/chats/' + str(chat)

	# create the folders for the chat if they don't exist
	if not os.path.isdir(chatDir):
		if not os.path.isdir('data/chats'):
			if not os.path.isdir('data'):
				os.mkdir('data')

			os.mkdir('data/chats')

		os.mkdir(chatDir)

	# Establish connection
	conn = sqlite3.connect(chatDir + '/' + 'chainStore.db')
	c = conn.cursor()

	for word1 in chainStore:
		word1baseform = word1.replace(',','').replace('.','').replace('?','').replace('!','').replace('(','').replace(')','').replace('[','').replace(']','').replace('"','').replace('-','').replace('_','').lower()
		for word2 in chainStore[word1]:
			oldCount = chainStore[word1][word2]

			try:
				c.execute("INSERT INTO pairs (word1baseform, word1, word2, count) VALUES (?, ?, ?, ?)", (word1baseform, word1, word2, oldCount))
			except:
				c.execute("UPDATE pairs SET count = count + ? WHERE word1baseform = ? AND word1 = ? AND word2 = ?", (oldCount, word1baseform, word1, word2))

	conn.commit()
	conn.close()
	return


def tts(msg,kind):
	content_type, chat_type, chat = telepot.glance(msg, flavor="chat")
	chatDir = 'data/chats/' + str(chat)

	if kind == 'text':
		commandSplit = msg['text'].lower().strip().split(" ")
		if '@' in commandSplit[0]:
			ttsify = msg['text'].replace('/tts@apustavabot ', '')
		else:
			ttsify = msg['text'].replace('/tts ', '')

		if commandSplit[1] == '/markov' and len(commandSplit) is 2:
			msgNew = msg
			msgNew['text'] = msgNew['text'].replace('/markov','')
			ttsify = chainGeneration(msg['chat']['id'], 0, 'chat', msgNew)

		# manipulate message content to remove '/markov'
		elif commandSplit[1] == '/markov' and len(commandSplit) > 2:
			msgNew = msg
			msgNew['text'] = msgNew['text'].replace('/markov','')
			ttsify = chainGeneration(msg['chat']['id'], 0, 'chat', msgNew)

	elif kind == 'reply':
		ttsify = msg['reply_to_message']['text']

	# get defaultLanguage
	with open("data/chats/" + str(chat) +  "/settings.json") as jsonData:
		settingMap = json.load(jsonData)

		try:
			 defaultLanguage = settingMap['tts']['defaultLanguage']
		
		except KeyError:
			settingMap['tts'] = {}
			settingMap['tts']['defaultLanguage'] = 'fi'
			defaultLanguage = 'fi'

			with open("data/chats/" + str(chat) +  "/settings.json", 'w') as jsonData:
				json.dump(settingMap, jsonData, indent=4, sort_keys=True)

	tts = gTTS(ttsify, lang=defaultLanguage)
	with open(chatDir + '/tts.mp3', 'wb') as ttsFile:
		tts.write_to_fp(ttsFile)

	oggVoice = AudioSegment.from_file(chatDir + '/tts.mp3', format='mp3').export(chatDir + '/tts.ogg', format='ogg', codec='libopus')
	
	if kind == 'text':
		with open(chatDir + '/tts.ogg', 'rb') as ttsSend:
			bot.sendVoice(chat, voice=ttsSend, reply_to_message_id=msg['message_id'])
	else:
		with open(chatDir + '/tts.ogg', 'rb') as ttsSend:
			bot.sendVoice(chat, voice=ttsSend)

	os.remove(chatDir + '/tts.mp3')
	os.remove(chatDir + '/tts.ogg')
	return


def markov(msg, commandSplit, chat):
	chatDir = 'data/chats/' + str(chat)

	# check if we were given a seed
	if len(commandSplit) is 1: # if there's ONLY the command, just randomly pick a word
		if 'reply_to_message' not in msg:
			seedInput = False

		else:
			msgtext = msg['reply_to_message']['text']
			if msgtext[0] == '/':
				seedInput = False

			else:
				seedInput = True
			
				genmsg = ''
				msgSplit = msgtext.split(' ')
				seed = msgSplit[-1]

				for i in range(0, len(msgSplit) - 1):
					genmsg += msgSplit[i]

					if i == 0:
						if genmsg[0].isalpha():
							genmsg = genmsg.capitalize()
						else:
							pass
					
					if i is not len(msgSplit) - 2:
						genmsg += ' '
	
	else:
		seedInput = True
		genmsg = ''
		n = 0

		startIndex = 1
		for n in range(startIndex, len(commandSplit) - 1):
			genmsg += commandSplit[n]

			if n == startIndex:
				if genmsg[0].isalpha():
					genmsg = genmsg.capitalize()
				else:
					pass

			if n is not len(commandSplit) - 2:
				genmsg += ' '

		seed = commandSplit[-1]


	if seedInput is False:
		seed = False

	replymsg = chainGeneration(chat, seed)

	if seedInput is not False:
		replymsg = genmsg + ' ' + replymsg
	
	if replymsg is not None and len(replymsg) is not 0:
		bot.sendMessage(chat, replymsg)

	return


def chainGeneration(chat, seed):
	# chat directory
	chatDir = 'data/chats/' + str(chat)

	# Establish connection
	conn = sqlite3.connect(chatDir + '/' + 'chainStore.db')
	c = conn.cursor()

	# We'd usually cut off the sentence at a period, but ignore if the word is listed here
	ignorePeriod = ['esim.', 'vrt.', 'ns.', 'tri.', 'yms.', 'jne.', 'mm.', 'mr.', 'ms.', 'ts.', 'ym.', 'kys.']

	# if seed isn't false, generate the first word according to the seed
	seedGenSuccess = False
	if seed is not False: # if we are given a seed, check if it exists in the db.
		try:
			word1baseform = seed.replace(',','').replace('.','').replace('?','').replace('!','').replace('(','').replace(')','').replace('[','').replace(']','').replace('"','').replace('-','').replace('_','').lower()
			c.execute("SELECT word2, count FROM pairs WHERE word1baseform = ? AND word1 = ?", (word1baseform, seed))
		
		except Exception as e:
			if debugLog is True:
				logging.info(f'Exception in genmsg: {e}')
			return

		# check length of our query return; if 0, try all forms of the word. If not, continue into the regular loop.
		queryReturn = c.fetchall()
		if len(queryReturn) is 0:
			# find all word1's with the same baseform
			baseform = seed.replace(',','').replace('.','').replace('?','').replace('!','').replace('(','').replace(')','').replace('[','').replace(']','').replace('"','').replace('-','').replace('_','').lower()
			c.execute("SELECT word1, word2, count FROM pairs WHERE word1baseform = ?", (baseform,))

			queryReturn = c.fetchall()

			# Still nothing.
			if len(queryReturn) is 0:
				genmsg = seed
				seedGenSuccess = False

			# found words with the same baseform
			else:
				# sum all the counts
				countSum = 0
				for row in queryReturn:
					countSum += row[2]

				paths = {}
				for row in queryReturn:
					word2 = row[1]
					count = row[2]

					if word2 not in paths:
						paths[word2] = count/countSum
					else:
						paths[word2] = paths[word2] + count/countSum

				# weighed pick of word2; generate value we'll use for the choice
				maxSum = 0
				for key, value in paths.items():
					maxSum += value

				probFloat = random.uniform(0,maxSum)

				probSum = 0
				for key, value in paths.items():
					probSum += value
					if probSum >= probFloat: # choose this word
						nextWord = key
						break

				if len(nextWord) is not 0:
					if nextWord[0] == '>':
						separator = '\n'
					else:
						separator = ' '
				else:
					separator = ''

				genmsg = seed + separator + nextWord
				baseWord = nextWord
				seedGenSuccess = True

				# return if we get a '', which implies the end of a sentence
				if nextWord == '' and nextWord[-1] != ',':
					return genmsg

				try:
					if nextWord[-1] == '.':
						if nextWord.lower() not in ignorePeriod:
							return genmsg

					elif nextWord[-1] == '?' or nextWord[-1] == '!':
						return genmsg

				except IndexError as e: # used to catch empty words and pass them silently
					pass

		# queryReturn not empty for the seed word; do a pick and advance into the regular loop
		else:
			seedGenSuccess = True
			countSum = 0
			for row in queryReturn:
				countSum += row[1]

			paths = {}
			for row in queryReturn:
				word2 = row[0]
				count = row[1]

				if word2 != '': # avoid not generating anything after the seed
					if word2 not in paths:
						paths[word2] = float(count/countSum)
					else:
						paths[word2] = paths[word2] + float(count/countSum)

			if len(paths) is not 0:
				maxSum = 0
				for key, value in paths.items():
					maxSum += value

				probFloat = random.uniform(0,maxSum)
				probSum = 0

				i = 0
				for key, value in paths.items():
					probSum += value
					if probSum >= probFloat: # choose this word
						nextWord = key
						break
					i += 1

				if len(nextWord) is not 0:
					if nextWord[0] == '>':
						separator = '\n'
					else:
						separator = ' '
				else:
					separator = ''

				genmsg = seed + separator + nextWord
				baseWord = nextWord

				# return if we get a '', which implies the end of a sentence
				if nextWord == '' and nextWord[-1] != ',':
					return genmsg

				try:
					if nextWord[-1] == '.':
						if nextWord.lower() not in ignorePeriod:
							return genmsg

					elif nextWord[-1] == '?' or nextWord[-1] == '!':
						return genmsg

				except IndexError as e: # used to catch empty words and pass them silently
					pass
			
			else:
				seedGenSuccess = False

	# pick a random word as baseWord; if seedGenSuccess is True, we already have a baseWord.
	if seedGenSuccess is False and seed is not False:
		# pull a list from db -> choose random element -> baseWord
		c.execute("SELECT COUNT(*) AS cnt FROM pairs")
		cnt = c.fetchall()[0][0]
		rndIndex = random.randint(0, cnt-1)
		
		c.execute("SELECT word1 FROM pairs LIMIT ?, 1", (rndIndex,))
		baseWord = c.fetchall()[0][0]

		if len(baseWord) is not 0:
			if baseWord[0] == '>':
				separator = '\n'
			else:
				separator = ' '
		else:
			separator = ''

		genmsg = seed + separator + baseWord

	# if no seed was given, pick a word at random
	if seed is False:
		randomGenSuccess = False
		failCount = 0
		while randomGenSuccess is False:
			try:
				c.execute("SELECT COUNT(*) AS cnt FROM pairs")
			except sqlite3.OperationalError:
				bot.sendMessage(chat, 'Error: ryhmästä ei ole dataa. Kokeile lähettää tavallinen viesti ensin!')
				return

			cnt = c.fetchall()[0][0]
			rndIndex = random.randint(0,cnt-1)
			c.execute("SELECT word1 FROM pairs LIMIT ?, 1", (rndIndex,))

			# now we have a baseword
			baseWord = c.fetchall()[0][0]
			successfulBaseWord = baseWord

			# baseform of baseword
			baseform = baseWord.replace(',','').replace('.','').replace('?','').replace('!','').replace('(','').replace(')','').replace('[','').replace(']','').replace('"','').replace('-','').replace('_','').lower()

			# check if we have a way of continuing with the chosen baseWord; get all word2's with the same word1
			c.execute("SELECT word2, count FROM pairs WHERE word1baseform = ? AND word1 = ?", (baseform, baseWord))

			queryReturn = c.fetchall()
			if len(queryReturn) is 0:
				c.execute("SELECT word1, word2, count FROM pairs WHERE word1baseform = ?", (baseform,))
				queryReturn = c.fetchall()

				# Still nothing.
				if len(queryReturn) is 0:
					randomGenSuccess = False
				else:
					randomGenSuccess = True
			
			else:
				word2success = False
				word2list = []
				for line in queryReturn:
					word2 = line[0]
					word2success = True
					if word2 not in word2list:
						word2list.append(word2)

				if word2success is True:
					randomGenSuccess = True
					nextWord = random.choice(word2list)

			if randomGenSuccess is False:
				failCount += 1
				pass

		baseWord = nextWord
		if len(baseWord) is not 0:
			if baseWord[0] == '>':
				separator = '\n'
			else:
				separator = ' '
		else:
			separator = ''

		if successfulBaseWord[0].isalpha():
			genmsg = successfulBaseWord.capitalize() + separator + nextWord
		else:
			genmsg = successfulBaseWord + separator + nextWord

	# now we're 100% certain we have a baseWord; start regular sentence generation
	# generate a random sentence length
	maxLength = random.randint(1, 25)
	genmsgLen = len(genmsg.split(' '))
	while genmsgLen < maxLength:
		genmsgLen = len(genmsg.split(' '))
		baseform = baseWord.replace(',','').replace('.','').replace('?','').replace('!','').replace('(','').replace(')','').replace('[','').replace(']','').replace('"','').replace('-','').replace('_','').lower()
		c.execute("SELECT word2, count FROM pairs WHERE word1baseform = ? AND word1 = ?", (baseform, baseWord))

		queryReturn = c.fetchall()

		# if we find nothing, try with baseform
		if len(queryReturn) is 0:
			# find all word1's with the same baseform
			baseform = baseWord.replace(',','').replace('.','').replace('?','').replace('!','').replace('(','').replace(')','').replace('[','').replace(']','').replace('"','').replace('-','').replace('_','').lower()

			c.execute("SELECT word1, word2, count FROM pairs WHERE word1baseform = ?", (baseform,))

			queryReturn = c.fetchall()

			# Still nothing.
			if len(queryReturn) is 0:
				return genmsg

			else: # found words with the same baseform
				countSum = 0 # sum all the counts
				for row in queryReturn:
					countSum += row[2]

				paths = {}
				for row in queryReturn:
					word2 = row[1]
					count = row[2]

					if word2 not in paths:
						paths[word2] = count/countSum
					else:
						paths[word2] = paths[word2] + count/countSum

				# weighed pick of word2; generate value we'll use for the choice
				maxSum = 0
				for key, value in paths.items():
					maxSum += value

				probFloat = random.uniform(0,maxSum)
				probSum = 0

				probSum = 0
				for key, value in paths.items():
					probSum += value
					if probSum >= probFloat: # choose this word
						nextWord = key
						break

				if len(nextWord) is not 0:
					if nextWord[0] == '>':
						separator = '\n'
					else:
						separator = ' '
				else:
					separator = ''

				genmsg = genmsg + separator + nextWord
				baseWord = nextWord

				# return if we get a '', which implies the end of a sentence
				if nextWord == '':
					return genmsg

				try:
					if nextWord[-1] == '.':
						if nextWord.lower() not in ignorePeriod:
							return genmsg

					elif nextWord[-1] == '?' or nextWord[-1] == '!':
						return genmsg

				except IndexError as e: # used to catch empty words and pass them silently
					pass

		else:
			# sum all the counts
			countSum = 0
			for row in queryReturn:
				countSum += row[1]

			paths = {}
			for row in queryReturn:
				word2 = row[0]
				count = row[1]

				if word2 not in paths:
					paths[word2] = count/countSum
				else:
					paths[word2] = paths[word2] + count/countSum

			maxSum = 0
			for key, value in paths.items():
				maxSum += value

			probFloat = random.uniform(0,maxSum)
			probSum = 0

			for key, value in paths.items():
				probSum += value
				if probSum >= probFloat: # choose this word
					nextWord = key
					break

			if len(nextWord) is not 0:
				if nextWord[0] == '>':
					separator = '\n'
				else:
					separator = ' '
			else:
				separator = ''

			genmsg = genmsg + separator + nextWord
			baseWord = nextWord

			if len(baseWord) > 0:
				if baseWord[-1] == ',':
					maxLength += 1

			# return if we get a '', which implies the end of a sentence
			if nextWord == '':
				return genmsg

			try:
				if nextWord[-1] == '.':
					if nextWord.lower() not in ignorePeriod:
						return genmsg

				elif nextWord[-1] == '?' or nextWord[-1] == '!':
					return genmsg

			except IndexError as e: # used to catch empty words and pass them silently
				pass

	return genmsg


def roll(msg):
	content_type, chat_type, chat = telepot.glance(msg, flavor="chat")
	commandSplit = msg['text'].strip().split(" ")

	try:
		rollArg = commandSplit[1].lower()
	except IndexError:
		rollArg = 'ylis'
	
	validRollArgs = ['ylis', 'kolikko', 'noppa']

	if rollArg in validRollArgs:
		pass
	else:
		repStr = '🔀 *Käyttö: /roll [argumentti]*\nLisäargumentit: ylis, kolikko, noppa'
		bot.sendMessage(chat, repStr, parse_mode="Markdown")
		return

	# generate an 8-digit random number sequence
	if rollArg == 'ylis':
		randInt = str(random.randint(10000000,99999999))

		# check if tuplat, triplat etc.
		n = 0
		for i in range(7,0,-1):
			if randInt[i] == randInt[i-1]:
				n += 1
			else:
				break

		repStr = randInt

		if n == 1:
			repStr += ', tuplat! ✌️'
		elif n == 2:
			repStr += ', triplat! 🔥'
		elif n > 3:
			repStr += '\n\nSuoraan sanottuna sairaat setit 😨'

	# int between 0 and 1
	elif rollArg == 'kolikko':
		randInt = random.randint(0,1)
		if randInt is 0:
			repStr = 'Kruuna'
		else:
			repStr = 'Klaava'

	# int between 1 and 6
	elif rollArg == 'noppa':
		randInt = random.randint(1,6)
		repStr = 'Noppa pyörii... Luku on {:d}.'.format(randInt)

	if 'reply_to_message' in msg:
		bot.sendMessage(chat, repStr, reply_to_message_id=msg['reply_to_message']['message_id'])
	else:
		bot.sendMessage(chat, repStr, reply_to_message_id=msg['message_id'])


def um():
	# 0 = uhka, 1 = mahdollisuus
	randInt = random.randint(0,1)
	
	responses = [
	'Absoluuttinen', 'Eittämätön', 'Kiistaton', 'Varma', 'Ehdoton', 'Vissi', 'Ehdoton, kiistämätön', 
	'Suurella todennäköisyydellä', 'Hyvin vahva', 'Potentiaalinen', 'Mahdollinen', 'Saletti',
	'Jysäyttävä', 'Todennäköisesti', 'Todennäköinen', 'Kristallipalloni sanoo', 'Tarot-korttini sanovat',
	'Aikaisempien kokemusten perusteella sanoisin', 'Jumalan antaman enteen mukaan', 'Pyöristyttävä',
	'Rusinat rasauttava', 'Tavanomainen', 'Ennustettavissa oleva', 'Todennäköisyysfunktioni sanoo',
	'Tähtien asennosta päätellen sanoisin', 'Lemmikkiaasini kivekset sanovat', 'Taikurin hatusta paljastuu',
	'Riimukiveni sanovat', 'Äitini sanoo että', 'Poikani mukaan kyseessä on', 'Satunnaisgeneroitu vastaus:',
	'Kysymyksellesi repeiltyäni sanoisin', 'Ei tarvitse kovinkaan suuri älykkö olla että näkee tämän olevan selvä',
	'Itseni keräiltyä sanoisin että', 'Taivaankappaleiden liikkeitä tulkittuani väittäisin että',
	'Kristallikiteestäni hohtaa', 'Ihmisuhrini muodostamassa savupilvessä näkyy', 'Kolmas silmäni sanoo',
	'Kahdestoista aistini olettaisi tämän olevan', 'Sykähti sen verran että tämä on ilmiselvä',
	'En kyl tiiä, sanoisin', 'Ilta-Sanomien horoskooppi sanoo', 'Kasipalloni piippaa:', 'Gaussin jakaumasta näemme tämän olevan',
	'Ratkaisun todistaminen jätetään lukijalle harjoitukseksi *', 'On ilmiselvää että kyseessä on',
	'Selvästi nähdään että vastaus on', 'Aiemmasta päätelmästä voidaan johtaa että tulos on',
	'Lottokone pyörii... Palloissa lukee', 'Tilastojen, faktojen ja analyysien jälkeen kyseessä on selkeä',
	'Viinapulloni pohjalta löydän totuuden:', 'Kuten isoäitini tapasi sanoa,', 'Olosuhteet huomioiden',
	'Keskusteluhistoriallesi myötisteltyäni sanoisin tämän olevan selvä', 'JA SIELTÄ! Kiistaton',
	'Kuten Matti Nykänen tapasi sanoa, jokainen tsäänssi on', 'Marakassejani ravisteltuani sanoisin',
	'Vuodenajasta poiketen sanoisin', 'Yleisesti pahuksuttu', 'Sending API request to Google.com... Got response:',
	'Jo muuan Jesse taisi sanoa tämän olevan', 'Wikipedia sanoo', 'Olen aika varma että tämä on juutalaisten juoni, eli',
	'WolframAlpha väittää tämän olevan', 'No mitäpä lottoat? Aivan selkeä', 'Mieluummin nyrkki perseessä kuin väittää etteikö tämä olisi',
	'Vierasvallan tietoverkossa suorittamani laskenta antaa odotusarvoksi', '[MESSAGE INTERCEPTED BY NSA PRISM CHECKPOINT] ORIGINAL PAYLOAD CONTENT:',
	'Heitän imaginääristä kolikkoa:', 'Nuuh nuuh... Haistan tämän olevan', 'Pikkulintuni lauloivat tämän olevan', 'Tinder-matchini sanoo',
	'Pimpelipom *tähtisadetta* *ilmatöötit laulavat* *Jeesus tulee toistamiseen*:', '[Ylidramatisointi satunnaisgeneroidusta vastauksesta]:',
	'Entten tentten teelikamentten, hissun kissun vaapula vissun, eelin keelin klot, viipula vaapula vot, Eskon saun piun paun. Nyt sää lähdet tästä pelistä pois, puh pah pelistä pois! Jäljelle jäi',
	'Kiinnostuskiikareissani näkyy']

	if randInt is 0:
		random.shuffle(responses)
		respStr = responses[0] + " uhka."

	else:
		random.shuffle(responses)
		respStr = responses[0] + " mahdollisuus."

	return respStr


def tuet(msg):
	# today
	today = date.today()
	todayWeekday = today.weekday()

	# check if there has been a tukiDate this month
	# there has already been one, if current date is greater than the first tukiDate this month
	tukiDate1 = datetime.date(today.year, today.month, 1)
	tukiDate1Weekday = tukiDate1.weekday()
	if tukiDate1Weekday > 5:
		tukiDate1 = date(tukiDate1.year, tukiDate1.month, tukiDate1.day+(7-tukiWeekday))

	# perform check for a possible holiday
	if date(tukiDate1.year,tukiDate1.month,tukiDate1.day) in holidays.FI():
		while date(tukiDate1.year,tukiDate1.month,tukiDate1.day) in holidays.FI() or tukiDate1.day > 5:
			tukiDate1 = date(tukiDate1.year, tukiDate1.month, tukiDate1.day+1)

	# now we have the first tukiDate of this month; check if we're past that. If it's today, reply accordingly
	dateDelta = tukiDate1 - today
	dayDelta = dateDelta.days

	if dayDelta is 0 and tukiDate1.month not in range(6,9):
		timeToTukiDate = 0
		header = "🎉*Minä kun tuet tulee tänään🎉\n*"
		mid = "https://www.youtube.com/watch?v=WQ9tcPSkfJU"
		replymsg = header + mid
		return replymsg

	elif tukiDate1.month in range(6,9):
		tukiDate2 = date(today.year, 9, 1)
		tukiWeekday = tukiDate2.weekday()
		if tukiWeekday > 5:
			tukiDate2 = date(tukiDate2.year, tukiDate2.month, tukiDate2.day+(7-tukiWeekday))

		if date(tukiDate2.year,tukiDate2.month,tukiDate2.day) in holidays.FI():
			while date(tukiDate2.year,tukiDate2.month,tukiDate2.day) in holidays.FI() or tukiDate2.day > 5:
				tukiDate2 = date(tukiDate2.year, tukiDate2.month, tukiDate2.day+1)

		timeToTukiDate = abs(tukiDate2 - today)

	# tukiDate is this month
	elif dayDelta > 0:
		timeToTukiDate = abs(tukiDate1 - today)
		tukiDate2 = tukiDate1
		tukiWeekday = tukiDate2.weekday()

	# tukiDate assuming there has already been a tukiDate this month; jump forward by a month
	elif dayDelta < 0:
		if today.month < 12:
			tukiDate2 = date(today.year, today.month+1, 1) # if it's November or less, it's this year
			if tukiDate2.month > 5 and tukiDate2.month < 9: # if it's summertime, skip to September
				tukiDate2 = date(today.year, 9, 1)
		else:
			tukiDate2 = date(today.year+1, 1, 1) # if it's december, next date is next year

		# check weekday the first day of the next month lands on
		tukiWeekday = tukiDate2.weekday()
		if tukiWeekday > 5:
			tukiDate2 = date(tukiDate2.year, tukiDate2.month, tukiDate2.day+(7-tukiWeekday))

		if date(tukiDate2.year,tukiDate2.month,tukiDate2.day) in holidays.FI():
			while date(tukiDate2.year,tukiDate2.month,tukiDate2.day) in holidays.FI() or tukiDate2.day > 5:
				tukiDate2 = date(tukiDate2.year, tukiDate2.month, tukiDate2.day+1)

		timeToTukiDate = abs(tukiDate2 - today)

	tukiWeekday = tukiDate2.weekday()
	if tukiWeekday is 0:
		viikonpaiva = "maanantai"
	elif tukiWeekday is 1:
		viikonpaiva = "tiistai"
	elif tukiWeekday is 2:
		viikonpaiva = "keskiviikko"
	elif tukiWeekday is 3:
		viikonpaiva = "torstai"
	elif tukiWeekday is 4:
		viikonpaiva = "perjantai"

	# construct a nice message
	if timeToTukiDate.days > 0 and timeToTukiDate.days < 32:
		header = "📅 *Seuraava tukipäivä on {:s} {:d}.{:d}.*\n".format(viikonpaiva,tukiDate2.day,tukiDate2.month)
		if timeToTukiDate.days is not 1:
			mid = "Seuraaviin tukiin aikaa *{:s}* päivää.".format(str(timeToTukiDate.days))
		else:
			mid = "Seuraaviin tukiin aikaa *{:s}* päivä.".format(str(timeToTukiDate.days))
		replymsg = header + mid
	
	# if tukiDate's month is September, it's currently summertime; reply accordingly
	elif tukiDate2.month is 9 and today.month is not 9:
		time = datetime.datetime.today()
		if time.hour > 4 and time.hour < 18:
			header = "👷‍♂️ *Mikset ole töissä?*\n"
		else:
			header = "😴 *Suihkuun ja nukkumaan, huomenna töihin*\n"
		mid = "Seuraava tukipäivä on kesän jälkeen, {:s}na {:d}.{:d}.\n".format(viikonpaiva,tukiDate2.day,tukiDate2.month)
		low = "Seuraaviin tukiin aikaa *{:s}* päivää.".format(str(timeToTukiDate.days))
		replymsg = header + mid + low

	bot.sendMessage(msg['chat']['id'], replymsg, parse_mode="Markdown")
	


def weatherAPILoad(url):
	weatherResponse = urlopen(url).read().decode('UTF-8')
	weatherJSON = json.loads(weatherResponse)
	
	try:
		dataDir = 'data/weather/'
		fileString = dataDir + url.split('/2.5/')[1].split('?')[0] + '.json'

		with open(fileString, 'w') as weatherDataStore:
			json.dump(weatherJSON, weatherDataStore, indent=4)
	
	except FileNotFoundError:
		if not os.path.isdir('data/weather'):
			os.mkdir('data')

		if not os.path.isdir('data/weather'):
			os.mkdir('data/weather')

		with open(fileString, 'w') as weatherDataStore:
			json.dump(weatherJSON, weatherDataStore, indent=4)

	return


def saa(msg, runCount):
	# make dir for storing .jsons
	if not os.path.isdir('data/weather'):
		os.mkdir('data/weather')

	# for times
	today = datetime.datetime.today()
	timestamp = int(time.time())

	# check message for extra arguments
	commandSplit = msg['text'].strip().split(" ")

	if len(commandSplit) > 1:
		cityName = msg['text'].replace('/saa ', '').title()
		cityID = cityName.replace(' ','+').lower()
		queryType = 'search'

	else:
		content_type, chat_type, chat = telepot.glance(msg, flavor="chat")

		# load default city
		with open("data/chats/" + str(chat) +  "/settings.json") as jsonData:
			settingMap = json.load(jsonData)

		try:
			defaultCity = settingMap['saa']['defaultCity']
		
		except KeyError:
			defaultCity = 'Otaniemi'
			settingMap['saa'] = {}
			settingMap['saa']['defaultCity'] = 'Otaniemi'

			with open("data/chats/" + str(chat) +  "/settings.json", 'w') as jsonData:
				json.dump(settingMap, jsonData, indent=4, sort_keys=True)

		if defaultCity == 'Otaniemi':
			cityName = 'Otaniemi'
			cityID = '643522'
			cityID = f'?id={cityID}'
			queryType = 'id'

		else:
			cityName = defaultCity.title()
			cityID = cityName.replace(' ','+').lower()
			queryType = 'search'

	if cityName == 'Otaniemi':
		# data from outside.aalto.fi; used for temp, humidity, and pressure
		niemi = 'http://outside.aalto.fi'
		page = urlopen(niemi)
		soup = BeautifulSoup(page, 'html.parser')
		curr = soup.find(id='current')
		data = curr.text.strip()
		timesplit = data.split(":")
		datasplit = timesplit[1].split(",")

		temp = float(datasplit[0].split(" ")[1])
		humidity = float(datasplit[1].split(" ")[1])
		pressure = float(datasplit[2].split(" ")[1])
		lux = float(datasplit[3].split(" ")[1])

		timestr = time.localtime(time.time())
		if timestr[4] < 10:
		    timemin = str(0) + str(timestr[4])
		else:
		    timemin = str(timestr[4])

		timestr1 = "kello {:d}.{:s}".format(timestr[3],timemin)

	# api key to send
	apiAppend = '&APPID=' + WEATHERKEY

	# weather URLs
	if queryType == 'search':
		currWeatherURL = 'https://api.openweathermap.org/data/2.5/weather?q=' + quote(cityID) + apiAppend
		hourlyWeatherURL = 'http://api.openweathermap.org/data/2.5/forecast?q=' + quote(cityID) + '&lang=fi' + apiAppend
		UVIndexURL = f'https://api.openweathermap.org/data/2.5/uvi?lat=60.188&lon=24.832{apiAppend}'
		
		# handle quote()
		currWeatherURL = currWeatherURL.replace('%2B','+')
		hourlyWeatherURL = hourlyWeatherURL.replace('%2B','+')

	elif queryType == 'id':
		currWeatherURL = 'https://api.openweathermap.org/data/2.5/weather{:s}{:s}'.format(cityID,apiAppend)
		hourlyWeatherURL = 'http://api.openweathermap.org/data/2.5/forecast{:s}&lang=fi{:s}'.format(cityID,apiAppend)
		UVIndexURL = 'https://api.openweathermap.org/data/2.5/uvi?lat=60.188&lon=24.832{:s}'.format(apiAppend)

	# get data from OpenWeatherMap using multiple threads
	owmURLs = [currWeatherURL, hourlyWeatherURL]

	# when you need sunglasses
	UVconditions = ['800', '801', '802']

	if today.hour > 4 and today.hour < 22 and cityName == 'Otaniemi':
		owmURLs.append(UVIndexURL)


	# go through the two or three urls using multiple threads for a slight speedup (network sluggishness etc.)
	threads = 4
	pool = Pool(threads)

	try:
		pool.map(weatherAPILoad, owmURLs)
	except multiprocessing.pool.MaybeEncodingError:
		if runCount is 0:
			translation = translate(cityName,'en','auto').replace('to ', '')

			# modify message text content
			newCallString = '/saa ' + str(translation)
			msg['text'] = newCallString

			returnStr = saa(msg,1)
			return returnStr

		else:
			return '😟 Kaupunkia ei löytynyt – kokeile uudestaan '

	# UV-index
	UVstr = ''
	if today.hour > 4 and today.hour < 21 and UVIndexURL in owmURLs:
		with open('data/weather/uvi.json', 'r') as weatherDataStore:
			weatherJSON = json.load(weatherDataStore)

		# Get levels
		UVIndexMagnitude = weatherJSON['value']

		# reply strings according to levels
		if int(UVIndexMagnitude) in range(0,3):
			UVstr = ''

		elif int(UVIndexMagnitude) in range(3,6):
			UVstr = '\n\n☀️ Kohtalainen UV-indeksi ({:.1f})\nMuista aurinkolasit! 😎'.format(UVIndexMagnitude)

		elif int(UVIndexMagnitude) in range(6,8):
			UVstr = '\n\n☀️ Voimakas UV-indeksi ({:.1f})\nMuista aurinkovoide ja aurinkolasit! 🍳'.format(UVIndexMagnitude)

		elif int(UVIndexMagnitude) in range(8,11):
			UVstr = '\n\n⚠️ *Hyvin voimakas UV-indeksi ({:.1f})*\nMuista aurinkovoide, suojaamaton iho palaa nopeasti!'.format(UVIndexMagnitude)

		elif int(UVIndexMagnitude) >= 11:
			UVstr = '\n\n⚠️🔥 *Äärimmäisen voimakas UV-indeksi ({:.1f})*\nSuojaa iho vaatetuksella, käytä aurinkolaseja!'.format(UVIndexMagnitude)


	# 3-hour forecast
	hourlyWeatherURL = 'http://api.openweathermap.org/data/2.5/forecast{:s}&lang=fi{:s}'.format(cityID,apiAppend)

	with open('data/weather/forecast.json', 'r') as weatherDataStore:
		weatherJSON = json.load(weatherDataStore)

	# parse forecast for rain and other extremities
	currHour = today.hour
	currForecastTimestamp = weatherJSON['list'][0]['dt']
	currForecastDate = datetime.datetime.fromtimestamp(currForecastTimestamp)
	currForecastEndHour = currForecastDate.hour
	ForecastValidityLeft = currForecastEndHour - currHour

	# weather condition for current 3-hour forecast
	weatherCond = weatherJSON['list'][0]['weather'][0]['main']
	rain = False # default

	# forecast valid for less than an hour; check the next 3 hours as well
	if ForecastValidityLeft < 1:
		weatherCondNext = weatherJSON['list'][1]['weather'][0]['main']
		if weatherCond == 'Rain' or weatherCondNext == 'Rain':
			rain = True
			try:
				precip = weatherJSON['list'][1]['rain']['3h']
				rainStr = "\n\n☔️ Sateita seuraavan kolmen tunnin aikana."
				precipStr = " Ennustettu sademäärä noin {:.2f} mm.".format(precip)
			except KeyError:
				precip = weatherJSON['list'][0]['rain']['3h']
				rainStr = "\n\n☔️ Sateita seuraavan tunnin aikana."
				precipStr = " Ennustettu sademäärä noin {:.2f} mm.".format(precip)

		elif weatherCond == 'Snow' or weatherCondNext == 'Snow':
			rain = True
			try:
				precip = weatherJSON['list'][1]['snow']['3h']
				rainStr = "\n\n❄️ Lumisateita seuraavan kolmen tunnin aikana."
				precipStr = " Ennustettu sademäärä noin {:.2f} mm.".format(precip)
			except KeyError:
				precip = weatherJSON['list'][0]['snow']['3h']
				rainStr = "\n\n❄️ Lumisateita seuraavan tunnin aikana."
				precipStr = " Ennustettu sademäärä noin {:.2f} mm.".format(precip)

	else:
		if ForecastValidityLeft is 1:
			tunnit = ''

		elif ForecastValidityLeft is 2:
			tunnit = 'kahden '

		elif ForecastValidityLeft is 3:
			tunnit = 'kolmen '

		# if there's rain within the next 3 hours, check if it continues.
		rainCount = 0
		snowCount = 0
		futurePrecip = 0.0

		for n in range(1,len(weatherJSON['list'])):
			futureForecast = weatherJSON['list'][n]
			futureCondition = futureForecast['weather'][0]['main']
			if futureCondition == 'Rain':
				rainCount += 1
				futurePrecip += futureForecast['rain']['3h']
			elif futureCondition == 'Snow':
				snowCount += 1
				futurePrecip += futureForecast['snow']['3h']
			else:
				break

		if rainCount is not 0 or snowCount is not 0:
			rainLength = ForecastValidityLeft + rainCount * 3 + snowCount * 3
			if rainLength < 11:
				if rainLength is 3:
					tunnit = 'kolmen '
				elif rainLength is 4:
					tunnit = 'neljän '
				elif rainLength is 5:
					tunnit = 'viiden '
				elif rainLength is 6:
					tunnit = 'kuuden '
				elif rainLength is 7:
					tunnit = 'seitsemän '
				elif rainLength is 8:
					tunnit = 'kahdeksan '
				elif rainLength is 9:
					tunnit = 'yhdeksän '
				elif rainLength is 10:
					tunnit = 'kymmenen '
			else:
				tunnit = str(rainLength) + ' '

		if weatherCond == 'Rain':
			rain = True
			precip = weatherJSON['list'][0]['rain']['3h']
			
			if rainCount is not 0 and snowCount is 0:
				rainStr = "\n\n☔️ Sateita seuraavan {:s}tunnin aikana.".format(tunnit)
				precip += futurePrecip

			elif snowCount is not 0 and rainCount is 0:
				rainStr = "\n\n☔️ Vesi- ja lumisateita seuraavan {:s}tunnin aikana.".format(tunnit)
				precip += futurePrecip

			elif snowCount is not 0 and rainCount is not 0:
				rainStr = "\n\n☔️ Vesi- ja lumisateita seuraavan {:s}tunnin aikana.".format(tunnit)
				precip += futurePrecip

			else:
				rainStr = "\n\n☔️ Sateita seuraavan {:s}tunnin aikana.".format(tunnit)
			
			precipStr = "\nEnnustettu sademäärä noin {:.2f} mm.".format(precip)

		elif weatherCond == 'Snow':
			rain = True
			precip = weatherJSON['list'][0]['snow']['3h']

			# snow in the future
			if rainCount is not 0 and snowCount is 0:
				rainStr = "\n\n☔️ Vesi- ja lumisateita seuraavan {:s}tunnin aikana.".format(tunnit)
				precip += futurePrecip

			# snow in the future
			elif snowCount is not 0 and rainCount is 0:
				rainStr = "\n\n❄️ Lumisateita seuraavan {:s}tunnin aikana.".format(tunnit)
				precip += futurePrecip

			# both rain and snow in the future
			elif snowCount is not 0 and rainCount is not 0:
				rainStr = "\n\n☔️ Vesi- ja lumisateita seuraavan {:s}tunnin aikana.".format(tunnit)
				precip += futurePrecip

			# nothing in the near-future
			else:		
				rainStr = "\n\n❄️ Lumisateita seuraavan {:s}tunnin aikana.".format(tunnit)
			
			precipStr = " Ennustettu sademäärä noin {:.2f} mm.".format(precip)

	if rain is False:
		rainStr = ''
		precipStr = ''

	# current weather
	currWeatherURL = 'https://api.openweathermap.org/data/2.5/weather{:s}{:s}'.format(cityID,apiAppend)

	with open('data/weather/weather.json', 'r') as weatherDataStore:
		weatherJSON = json.load(weatherDataStore)

	# extract the data we want 
	iconID = str(weatherJSON['weather'][0]['id'])
	description = weatherJSON['weather'][0]['description']
	wind = weatherJSON['wind']['speed']
	timezone = weatherJSON['timezone'] # seconds from UTC
	countryCode = weatherJSON['sys']['country']

	if countryCode != 'FI':
		UTCTime = pytz.utc.localize(datetime.datetime.utcnow())
		
		if timezone % 3600 == 0:
			localTimeHourAdj = timezone / 3600
			localTimeMinAdj = 0
			localTimeMins = UTCTime.minute
		else:
			localTimeMinAdj = timezone % 3600
			localTimeHourAdj = (timezone - localTimeMinAdj) / 3600

		localTimeHours = UTCTime.hour + localTimeHourAdj
		if localTimeMinAdj + UTCTime.minute >= 60:
			localTimeHours += 1
			localTimeMins = UTCTime.minute + localTimeMinAdj - 60
		else:
			localTimeMins = UTCTime.minute + localTimeMinAdj

		if localTimeHours >= 24:
			localTimeHours = localTimeHours - 24

		elif localTimeHours < 0:
			localTimeHours = localTimeHours + 24 # ex. -2:00 = 22:00 -> -2 + 24 = 22

		timezoneHr = float(timezone / 3600)

		if timezone % 3600 != 0:
			if timezoneHr >= 0:
				timeZoneStr = '+{:.1f}'.format(timezoneHr)
			else:
				timeZoneStr = '{:.1f}'.format(timezoneHr)
		else:
			if timezoneHr >= 0:
				timeZoneStr = '+{:d}'.format(int(timezoneHr))
			else:
				timeZoneStr = '{:d}'.format(int(timezoneHr))

		if localTimeMins < 10:
			localTimeMins = '0' + str(localTimeMins)

		timeStr = f'\n\n🕓 Paikallinen kellonaika {int(localTimeHours)}.{localTimeMins} (UTC{timeZoneStr})'

	sunriseTimestamp = weatherJSON['sys']['sunrise']
	sunsetTimestamp = weatherJSON['sys']['sunset']
	sunrise = datetime.datetime.fromtimestamp(weatherJSON['sys']['sunrise'])
	sunset = datetime.datetime.fromtimestamp(weatherJSON['sys']['sunset'])

	if cityName != 'Otaniemi':
		temp = float(weatherJSON['main']['temp']) - 273.15
		pressure = float(weatherJSON['main']['pressure'])
		humidity = float(weatherJSON['main']['humidity'])

	if timestamp > sunriseTimestamp:
		timeToSunrise = -1
	else:
		timeToSunrise = abs(today - sunrise)

	if timestamp > sunsetTimestamp:
		timeToSunset = -1
	else:
		timeToSunset = abs(today - sunset)

	if timeToSunrise is not -1:
		nextSun = 'sunrise'
	elif timeToSunrise is -1 and timeToSunset is not -1:
		nextSun = 'sunset'
	else:
		nextSun = 'sunrise'

	# handle conditions with no wind at all
	windDesc = ''
	try:
		windDir = weatherJSON['wind']['deg']
	except KeyError:
		windDir = -1
		windDesc = ''

	# wind directions
	if windDir in range(0,int(22.5)):
		windDesc = 'pohjois'
	elif windDir in range(int(22.5),int(67.5)):
		windDesc = 'koillis'
	elif windDir in range(int(67.5),int(112.5)):
		windDesc = 'itä'
	elif windDir in range(int(112.5),int(157.5)):
		windDesc = 'kaakkois'
	elif windDir in range(int(157.5),int(202.5)):
		windDesc = 'etelä'
	elif windDir in range(int(202.5),int(247.5)):
		windDesc = 'lounais'
	elif windDir in range(int(247.5),int(292.5)):
		windDesc = 'länsi'
	elif windDir in range(int(292.5),int(337.5)):
		windDesc = 'luoteis'
	elif windDir in range(int(337.5),int(360)):
		windDesc = 'pohjois'

	# wind speeds
	windInt = int(wind)
	if windInt in range(0,4):
		windSpeedDesc = 'Heikko'
	elif windInt in range(4,8):
		windSpeedDesc = 'Kohtalainen'
	elif windInt in range(8,14):
		windSpeedDesc = 'Navakka'
	elif windInt in range(14,21):
		windSpeedDesc = 'Kova'
	elif windInt in range(21,25):
		windSpeedDesc = '⚠️ Myrskyinen'
	elif windInt in range(25,29):
		windSpeedDesc = '⚠️ *Hyvin myrskyinen*'
	elif windInt in range(29,32):
		windSpeedDesc = '⚠️ *Äärimmäisen myrskyinen*'
	elif windInt >= 32:
		windSpeedDesc = '⚠️ *Hirmumyrskyinen*'

	# weather descriptions
	weatherDescriptions = {}
	
	weatherDescriptions['thunderstorm with light rain'] = 'ukkosta ja kevyttä sadetta'
	weatherDescriptions['thunderstorm with rain'] = 'ukkosta ja sadetta'
	weatherDescriptions['thunderstorm with heavy rain'] = 'ukkosmyrskyjä ja voimakasta sadetta'
	weatherDescriptions['light thunderstorm'] = 'kevyttä ukkosta'
	weatherDescriptions['thunderstorm'] = 'ukkosta'
	weatherDescriptions['heavy thunderstorm'] = 'voimakkaita ukkosmyrskyjä'
	weatherDescriptions['ragged thunderstorm'] = 'myrskyistä ukkosta'
	weatherDescriptions['thunderstorm with light drizzle'] = 'ukkosta ja kevyttä tihkusadetta'
	weatherDescriptions['thunderstorm with drizzle'] = 'ukkosta ja tihkusadetta'
	weatherDescriptions['thunderstorm with heavy drizzle'] = 'ukkosta ja voimakasta tihkusadetta'
	weatherDescriptions['light intensity drizzle'] = 'pientä tihkusadetta'
	weatherDescriptions['drizzle'] = 'tihkusadetta'
	weatherDescriptions['heavy intensity drizzle'] = 'voimakasta tihkusadetta'
	weatherDescriptions['light intensity drizzle rain'] = 'pientä tihkusadetta'
	weatherDescriptions['drizzle rain'] = 'tihkusadetta'
	weatherDescriptions['heavy intensity drizzle rain'] = 'voimakasta tihkusadetta'
	weatherDescriptions['shower rain and drizzle'] = 'sadekuuroja ja tihkua'
	weatherDescriptions['heavy shower rain and drizzle'] = 'voimakkaita sadekuuroja ja tihkua'
	weatherDescriptions['shower drizzle'] = 'tihkusadekuuroja'
	weatherDescriptions['light rain'] = 'kevyttä sadetta'
	weatherDescriptions['moderate rain'] = 'sadetta'
	weatherDescriptions['heavy intensity rain'] = 'voimakkaita sateita'
	weatherDescriptions['very heavy rain'] = 'hyvin voimakkaita sateita'
	weatherDescriptions['extreme rain'] = 'äärimmäisiä sateita'
	weatherDescriptions['freezing rain'] = 'jäätävää sadetta'
	weatherDescriptions['light intensity shower rain'] = 'kevyitä sadekuuroja'
	weatherDescriptions['shower rain'] = 'sadekuuroja'
	weatherDescriptions['heavy intensity shower rain'] = 'voimakkaita sadekuuroja'
	weatherDescriptions['ragged shower rain'] = 'myrskyisiä sadekuuroja'
	weatherDescriptions['light snow'] = 'kevyttä lumisadetta'
	weatherDescriptions['snow'] = 'lumisadetta'
	weatherDescriptions['heavy snow'] = 'voimakasta lumisadetta'
	weatherDescriptions['sleet'] = 'räntäsadetta'
	weatherDescriptions['light shower sleet'] = 'kevyitä räntäkuuroja'
	weatherDescriptions['shower sleet'] = 'räntäkuuroja'
	weatherDescriptions['light rain and snow'] = 'kevyttä vesi- ja lumisadetta'
	weatherDescriptions['rain and snow'] = 'lumi- ja vesisateita'
	weatherDescriptions['light shower snow'] = 'kevyitä lumisadekuuroja'
	weatherDescriptions['shower snow'] = 'lumisadekuuroja'
	weatherDescriptions['heavy shower snow'] = 'voimakkaita lumisadekuuroja'
	weatherDescriptions['mist'] = 'usvaista'
	weatherDescriptions['smoke'] = 'savuista'
	weatherDescriptions['haze'] = 'utuista'
	weatherDescriptions['sand/ dust whirls'] = 'hiekka-/pölypyörteitä'
	weatherDescriptions['fog'] = 'sumuista'
	weatherDescriptions['sand'] = 'ilmassa hiekkaa'
	weatherDescriptions['dust'] = 'ilmassa pölyä'
	weatherDescriptions['volcanic ash'] = 'ilmassa vulkaanista tuhkaa'
	weatherDescriptions['squalls'] = 'tuulenpuuskia'
	weatherDescriptions['tornado'] = 'tornadoja'
	weatherDescriptions['clear sky'] = 'kirkas, pilvetön taivas'
	weatherDescriptions['few clouds'] = 'poutapilviä'
	weatherDescriptions['scattered clouds'] = 'hajanaisia pilviä'
	weatherDescriptions['broken clouds'] = 'rakoileva pilvipeite'
	weatherDescriptions['overcast clouds'] = 'pilvinen sää'

	# Finnish weather description
	finnWeatherDesc = weatherDescriptions[description]

	# weather icons
	weatherIcons = {}

	# rain
	weatherIcons['2'] = '⛈' 	# thunderstorms
	weatherIcons['3'] = '🌧' 	# drizzle
	weatherIcons['5'] = '🌧'	# rain
	weatherIcons['6'] = '🌨'	# snow
	weatherIcons['7'] = '🌫'	# fog/mist/etc.
	
	# clear
	weatherIcons['800'] = {}
	weatherIcons['800']['day'] = '☀️'
	weatherIcons['800']['night'] = '🌌'

	# cloudy
	weatherIcons['801'] = {}
	weatherIcons['801']['day'] = '🌤'
	weatherIcons['801']['night'] = '🌒'

	weatherIcons['802'] = {}
	weatherIcons['802']['day'] = '⛅️'
	weatherIcons['802']['night'] = '☁️'
	
	weatherIcons['803'] = {}
	weatherIcons['803']['day'] = '🌥'
	weatherIcons['803']['night'] = '☁️'
	
	weatherIcons['804'] = {}
	weatherIcons['804']['day'] = '☁️'
	weatherIcons['804']['night'] = '☁️'

	# choose which icon to use
	if iconID[0] in ['2','3','5','6','7']:
		weatherIcon = weatherIcons[iconID[0]]

	elif iconID[0] == '8':
		if datetime.datetime.today().hour in range(7,22):
			weatherIcon = weatherIcons[iconID]['day']
		else:
			weatherIcon = weatherIcons[iconID]['night']

	else:
		weatherIcon = '❔'

	if temp <= -20:
		feelslike = 'arktinen'
	elif temp <= -15 and temp >= -19:
		feelslike = 'jäätävä'
	elif temp < -5 and temp > -15:
		feelslike = 'rapsakka'
	elif temp >= -5 and temp < 5:
		feelslike = 'viileä'
	elif temp >= 5 and temp < 12:
		feelslike = 'keväinen'
	elif temp >= 12 and temp < 15:
		feelslike = 'wappuinen'
	elif temp >= 15 and temp < 22:
		feelslike = 'kesäisen lämmin'
	elif temp >= 21 and temp <= 25:
		feelslike = 'kesäinen'
	elif temp > 25 and temp < 28:
		feelslike = 'helteinen'
	elif temp >= 28:
		feelslike = 'paahtava'

	# weatherIcon for sunset and sunrise, if it's clear
	sunRepstr = ''
	if iconID[0] == '8':
		if nextSun == 'sunrise' and timeToSunrise is not -1:
			#if timeToSunrise.seconds <= 1800*(3/2):
				#weatherIcon = '🌄'
			if timeToSunrise.seconds <= 3600*2:
				if timeToSunrise.seconds <= 3600:
					timeString = int(timeToSunrise.seconds/60)
					sunRepstr = f'\n\n🌄 Auringonnousuun {timeString} minuuttia.'
				else:
					minTime = int((timeToSunrise.seconds - 3600)/60)
					timeString = f'tunti ja {minTime} minuuttia'
					sunRepstr = f'\n\n🌄 Auringonnousuun {timeString}.'

		elif nextSun == 'sunset':
			#if timeToSunset.seconds <= 1800*(3/2):
			#	weatherIcon = '🌅'
			if timeToSunset.seconds <= 3600:
				timeString = int(timeToSunset.seconds/60)
				sunRepstr = f'\n\n🌅 Auringonlaskuun {timeString} minuuttia.'

			elif abs(today - sunrise).seconds <= 3600:
				timeDelta = abs(today - sunrise)
				timeString = int(timeDelta.seconds/60)
				sunRepstr = f'\n\n🌄 Aurinko nousi {timeString} minuuttia sitten.'

		elif timeToSunset == -1:
			if abs(today - sunset).seconds <= 3600:
				timeDelta = abs(today - sunset)
				timeString = int(timeDelta.seconds/60)
				sunRepstr = f'\n\n🌅 Aurinko laski {timeString} minuuttia sitten.'


	# construct the message
	if cityName == 'Otaniemi':
		header = "{:s} *Otaniemessä {:s}*\n".format(weatherIcon,finnWeatherDesc)
	else:
		header = f'{weatherIcon} *{cityName} – {finnWeatherDesc}*\n'

	tempStr = "Lämpötila on {:s} {:+.1f} °C.".format(feelslike,temp)

	mid = "\n{:s} {:.1f} m/s {:s}tuuli.\n".format(windSpeedDesc,wind,windDesc)
	hp = "Ilmanpaine on {:.1f} hPa.\nIlmankosteus on {:.1f} RH%.".format(pressure,humidity)
	
	if countryCode != 'FI':
		weatherReply = header + tempStr + mid + hp + rainStr + precipStr + timeStr
	else:
		weatherReply = header + tempStr + mid + hp + rainStr + precipStr

	# check if we need to include the UV-index string
	if UVstr != '' and iconID in UVconditions:
		if timeToSunrise is -1:
			if timeToSunset.seconds >= 0:
				weatherReply = weatherReply + UVstr
		else:
			if timeToSunrise.seconds < 3600*2:
				weatherReply = weatherReply + UVstr

	if sunRepstr != '':
		if countryCode != 'FI':
			sunRepstr = sunRepstr.replace('\n\n', '\n')
			weatherReply = weatherReply + sunRepstr
		else:
			weatherReply = weatherReply + sunRepstr

	return weatherReply


def webcam(msg):
	content_type, chat_type, chat = telepot.glance(msg, flavor="chat")
	commandSplit = msg['text'].strip().split(" ")

	try:
		location = commandSplit[1].lower()
	except IndexError:
		bot.sendChatAction(chat, action='typing')

		replyMsg = '*📷 Käyttö: /webcam [kameran nimi]*\nKamerat: Väre (väre), Maarintie 13 (mt13)\n'
		replyMsg = replyMsg + '_Kameroita ylläpitää Aalto-yliopisto – kuvat päivittyvät vartin välein._'
		bot.sendMessage(chat_id=chat, text=replyMsg, parse_mode="Markdown")

		return

	# väre = väre1
	validCams = {'väre':'http://vare-cam.aalto.fi/latest.jpg',
	'mt13': 'http://mt13-cam.aalto.fi/latest.jpg',
	'maarintie': 'http://mt13-cam.aalto.fi/latest.jpg'}

	# feeds are updated once an hour; get the current hour
	today = datetime.datetime.now()
	month = today.month
	day = today.day
	hour = today.hour
	minute = today.minute

	if minute in range(0,15):
		minute = '00'
	elif minute in range(15,30):
		minute = '15'
	elif minute in range(30,45):
		minute = '30'
	elif minute in range(45,60):
		minute = '45'

	if not os.path.isdir('data/webcam'):
		os.mkdir('data/webcam')

	if location in validCams:
		bot.sendChatAction(chat, action='upload_photo')
		if location == 'väre' or location == 'väre1': # väre or väre1
			# retrieve image first, because Telegram won't apparently do that for us
			urllib.request.urlretrieve(validCams['väre'], 'data/webcam/vare.jpg')
			with open('data/webcam/vare.jpg', 'rb') as image:
				captionText = '📷 Väre – {:d}.{:d}. kello {:d}.{:s}'.format(day,month,hour,minute)
				bot.sendPhoto(chat_id=chat, photo=image, caption=captionText)

		elif location == 'väre2' or location == 'mt13' or location == 'maarintie': # väre2
			urllib.request.urlretrieve(validCams['mt13'], 'data/webcam/mt13.jpg')
			with open('data/webcam/mt13.jpg', 'rb') as image:
				captionText = '📷 Maarintie 13 – {:d}.{:d}. kello {:d}.{:s}'.format(day,month,hour,minute)
				bot.sendPhoto(chat_id=chat, photo=image, caption=captionText)

	else:
		bot.sendChatAction(chat, action='typing')
		replyMsg = '*📷 Käyttö: /webcam [kameran nimi]*\nKamerat: Väre (väre), Maarintie 13 (mt13)\n'
		replyMsg = replyMsg + '_Kameroita ylläpitää Aalto-yliopisto – kuvat päivittyvät vartin välein._'
		bot.sendMessage(chat_id=chat, text=replyMsg, parse_mode="Markdown")



def replace(msg):
	# split command first by taking /s and trailing whitespace out (so 3 chars)
	arg12 = msg['text'][3:]

	# now split arg12 into arg1 and arg2 by splitting via "--"
	try:
		args = arg12.split(' > ', 1)
		arg1 = args[0].strip()
		arg2 = args[1].strip()

		try:
			old_text = msg['reply_to_message']['text']
		except KeyError:
			replyMsg = '*🔀 Käyttö: /s [korvattava teksti] > [uusi teksti]*\nKomento korvaa viestissä johon vastaat tekstin #1 tekstillä #2.'
			bot.sendMessage(msg['chat']['id'], text=replyMsg, parse_mode='Markdown')
			return

		# check if substring exists
		if arg1 in old_text:
			bot.sendMessage(msg['chat']['id'], old_text.replace(arg1, arg2), reply_to_message_id=msg['reply_to_message']['message_id'])
			return
		else:
			if arg1.capitalize() in old_text:
				bot.sendMessage(msg['chat']['id'], old_text.replace(arg1.capitalize(), arg2), reply_to_message_id=msg['reply_to_message']['message_id'])
				return

			elif arg1.lower() in old_text:
				bot.sendMessage(msg['chat']['id'], old_text.replace(arg1.lower(), arg2), reply_to_message_id=msg['reply_to_message']['message_id'])
				return

	except IndexError:
		replyMsg = '*🔀 Käyttö: /s [korvattava teksti] > [uusi teksti]*\nKomento korvaa vastatussa viestissä tekstin #1 tekstillä #2.'
		bot.sendMessage(msg['chat']['id'], text=replyMsg, parse_mode='Markdown')
		return


# used by the thread-pool to parse Alko's webpages
def alkoCalc(pageURL):
    page = urlopen(pageURL)
    pageNum = pageURL.split('&PageNumber=')[1]
    soup = BeautifulSoup(page, 'html.parser')
    products = soup.find_all('div', class_='mini-card', id=True)

    productStore = {}
    productStore[storeName] = {}

    productCount = 0
    unDrinkable = 0
    for product in products:
        skip = False

        # dig product's ID from the html
        productID = product['id'].split('-')[2]

        # dig the cost of the product from the depths of the html
        productCost = float(product.find_all('span', {'class': 'price-wrapper mc-price hide-for-list-view hide-for-text-view'}, content=True)[0]['content'])

        # get product data from the html, but first deserialize it to a json object
        productData = json.loads(product.find_all('div', {'data-alkoproduct': productID}, {'data-product-data': True})[0]['data-product-data'])

        if productData['selection'] == 'tarvikevalikoima':
            skip = True

        if skip is False:
            # get some data from productData
            productID = int(productData['id'])
            name = productData['name'].replace('  ', ' ').strip()
            bottleSize = float(productData['size'].strip())
            alcVol = float(productData['alcohol'].strip()) / 100
            package = productData['packaging']
            category = productData['category']
            origin = productData['origin']
            greenChoice = productData['greenChoice']
            ethical = productData['ethical']

            if package == 'pullo':
                collateral = 0.1
            elif package == 'muovipullo':
                if bottleSize <= 0.35:
                    collateral = 0.1
                elif bottleSize > 0.35 and bottleSize < 1.0:
                    collateral = 0.2
                elif bottleSize >= 1.0:
                    collateral = 0.4
            elif package == 'tölkki':
                collateral = 0.15
            else:
                collateral = 0

            # calculate alcohol-for-buck -factor
            try:
                alcoFactor = ((productCost - collateral)/bottleSize)*(1/alcVol)
                alcoFactor = 1/alcoFactor
            except ZeroDivisionError:
                alcoFactor = 'Ei alkoholia'

            if alcoFactor is not 'Ei alkoholia':
                productStore[storeName][productID] = {}
                productStore[storeName][productID]['name'] = name
                productStore[storeName][productID]['category'] = category
                productStore[storeName][productID]['origin'] = origin
                productStore[storeName][productID]['greenChoice'] = greenChoice
                productStore[storeName][productID]['ethical'] = ethical
                productStore[storeName][productID]['price'] = productCost
                productStore[storeName][productID]['size'] = bottleSize
                productStore[storeName][productID]['alcohol'] = alcVol*100
                productStore[storeName][productID]['package'] = package
                productStore[storeName][productID]['collateral'] = collateral
                productStore[storeName][productID]['alcoFactor'] = alcoFactor

    with io.open('productCatalog.json', 'r', encoding='utf8') as catalog:
        oldProductStore = json.load(catalog)

    with io.open('productCatalog.json', 'w', encoding='utf8') as catalog:
        newProductStore = {**oldProductStore, **productStore}
        json.dump(newProductStore, catalog, indent=4, sort_keys=True)


    return



def alkoOpen():
    # open hours
    openHoursURL = 'https://www.alko.fi/myymalat-palvelut/2195'
    page = urlopen(openHoursURL)
    soup = BeautifulSoup(page, 'html.parser')
    openSoup = soup.find_all('div', {'class': 'column end opening-hours'})[0]
    openSoup = openSoup.find_all('div', {'class': 'now-future-wrapper relative'}, {'data-current-date': True})[0]
    dataDate = openSoup['data-current-date']

    # openings with date and weekday: ['weekday', 'date', 'hours']
    todayOpen = openSoup.find_all('span', {'class': 'opening-hours-item today'})[0].text.strip().replace('\n', ' ').split('  ')
    futureOpen = openSoup.find_all('span', {'class': 'opening-hours-item '})

    with open('openSoup.html', 'w') as html:
        html.write(openSoup.prettify())

    dateStore = {}
    dateStore[todayOpen[1]] = {}
    dateStore[todayOpen[1]]['weekday'] = todayOpen[0]
    dateStore[todayOpen[1]]['open'] = todayOpen[2]

    for date in futureOpen:
        date = date.text.strip().replace('\n', ' ').split(' ')
        tempEntryStore = []
        for entry in date:
            entry = entry.replace(' ', '')
            tempEntryStore.append(entry)

        dateStore[tempEntryStore[1]] = {}
        dateStore[tempEntryStore[1]]['weekday'] = tempEntryStore[0]
        dateStore[tempEntryStore[1]]['open'] = tempEntryStore[2]

    with io.open('openHours.json', 'w', encoding='utf8') as openHours:
        json.dump(dateStore, openHours, indent=4, sort_keys=False)

    # today datetime string; in the same form as the ones found in openHours.json
    today = str(datetime.datetime.today().day) + '.' + str(datetime.datetime.today().month)

    return


def alko():
    # return open hours for Otaniemi Alko
    # once done, print the default output (Otaniemi Alko's opening hours, top products, best alco-for-buck products)

    # open hours
    openHoursURL = 'https://www.alko.fi/myymalat-palvelut/2195'

    # catalog
    catalogURL = 'https://www.alko.fi/INTERSHOP/web/WFS/Alko-OnlineShop-Site/fi_FI/-/EUR/ViewParametricSearch-PagingAll?&SearchParameter=%26%40QueryTerm%3D*%26productInStore%3D2195'

    # store name
    global storeName 
    storeName = 'Alko Otaniemi'

    # page number string
    pageNumAppend = '&PageNumber='

    # dictionary for products
    productStore = {}
    productStore[storeName] = {}

    # generate catalog file
    with io.open('productCatalog.json', 'w', encoding='utf8') as catalog:
        json.dump(productStore,catalog)

    print('productCatalog.json generated!\n')

    # start time
    tStart = datetime.datetime.today()

    # get first page manually
    pageURL = catalogURL + pageNumAppend + '1'
    page = urlopen(pageURL)
    soup = BeautifulSoup(page, 'html.parser')
    products = soup.find_all('div', class_='mini-card', id=True)

     # get number of pages (number of products / 12 per page)
    pageNumSoup = soup.find_all('a', class_='num-products-text')[0].find_all('h3')
    nProducts = int(pageNumSoup[0].text.strip().split(' ')[0])
    nPages = math.ceil(nProducts/12)

    print(f'Products found: {nProducts}')
    print(f'Pages found: {nPages}')
    print('\nGenerating pool...\n')

    # generate addresses for pooling
    urls = []
    for n in range(1,nPages+1):
        url = catalogURL + pageNumAppend + str(n)
        urls.append(url)

    # generate pool
    threads = 4 # 2 physical cores, 4 virtual cores -> 4 threads @ 100% util.
    pool = Pool(threads)

    # start threads
    pool.map(alkoCalc, urls)

    tEnd = datetime.datetime.today()
    tElapsed = abs(tEnd - tStart)
    print(f'[Parsed {nPages} pages with {threads} threads – took {tElapsed.seconds} seconds]\n')

    return


def info(msg):
	content_type, chat_type, chat = telepot.glance(msg, flavor='chat')
	chatDir = 'data/chats/' + str(chat)

	# read stats db
	statsConn = sqlite3.connect('data/stats.db')
	statsCursor = statsConn.cursor()

	try: # pull global stats from db
		statsCursor.execute("SELECT msgCount, cmdCount FROM stats")

		# parse returned global data
		queryReturn = statsCursor.fetchall()
		if len(queryReturn) is not 0:
			globalMessages = 0
			globalCommands = 0
			for row in queryReturn:
				globalMessages += row[0]
				globalCommands += row[1]

		else:
			globalMessages = 0
			globalCommands = 0

	except sqlite3.OperationalError:
		globalMessages = 0
		globalCommands = 0

	try: # pull local stats from db
		statsCursor.execute("SELECT msgCount, cmdCount FROM stats WHERE chatID = ?", (chat,))

		# parse returned data
		queryReturn = statsCursor.fetchall()
		statsConn.close()

		if len(queryReturn) is not 0:
			messages = 0
			commands = 0
			for row in queryReturn:
				messages += row[0]
				commands += row[1]

		else:
			messages = 0
			commands = 0
	
	except sqlite3.OperationalError:
		messages = 0
		commands = 0

	# get system uptime
	up = uptime()
	updays = int(up/(3600*24))
	uphours = int((up-updays*3600*24)/(3600))
	upmins = int((up - updays*3600*24 - uphours*60*60)/(60))
	
	if upmins < 10:
		upmins = str(0) + str(upmins)
	else:
		upmins = str(upmins)

	# get chainStore.db file size
	try:
		chainStorePath = chatDir + '/chainStore.db'
		dbSize = float(os.path.getsize(chainStorePath) / 1000000)
	except:
		dbSize = 0.00

	infomsg1 = "Apustaja versio {:s}\n".format(versionumero)
	localStatsHeader = '*Ryhmän tilastot*\n'
	localStats1 = 'Viestejä käsitelty: {:d}\n'.format(messages)
	localStats2 = 'Komentoja käsitelty: {:d}\n'.format(commands)
	localdbsize = 'Markov-mallin koko: {:.2f} MB\n\n'.format(dbSize)

	globalStatsHeader = '*Yleiset tilastot*\n'
	globalStats1 = 'Viestejä käsitelty: {:d}\n'.format(globalMessages)
	globalStats2 = 'Komentoja käsitelty: {:d}\n'.format(globalCommands)

	today = datetime.datetime.now()
	hour = today.hour
	mins = today.minute

	if mins < 10:
		mins = str(0) + str(mins)
	else:
		mins = str(mins)
	
	if updays > 0:
		infomsg4 = "{:d}:{:s} up {:d} days, {:d}:{:s}\n".format(hour,mins,updays,uphours,upmins)
	else:
		infomsg4 = "{:d}:{:s}  up {:d}:{:s}\n".format(hour,mins,uphours,upmins)

	upstr = '\n*Palvelimen tiedot*\n'

	return localStatsHeader + localStats1 + localStats2 + localdbsize + globalStatsHeader + globalStats1 + globalStats2 + upstr + infomsg1 + infomsg4


def firstRun():
	print('Vaikuttaa siltä että ajat Apustajaa ensimmäistä kertaa')
	print('Aloitetaan luomalla tarvittavat kansiot.')
	time.sleep(2)
	
	# create /data and /chats
	if not os.path.isdir('data'):
		os.mkdir('data')
		os.mkdir('data/chats')
		print("Kansiot luotu!\n")

	elif not os.path.isdir('data/chats'):
		os.mkdir('data/chats')
		print("Kansiot luotu!\n")

	time.sleep(1)

	print('Apustaja tarvitsee toimiakseen ns. bot tokenin;')
	print('ohjeet tämän hankkimiseen löydät Githubista.')

	# create a settings file for the bot; we'll store the API keys here
	if not os.path.isfile('data' + '/botSettings.json'):
		if not os.path.isdir('data'):
			os.mkdir('data')

		with open('data/botSettings.json', 'w') as jsonData:
			settingMap = {} # empty .json file
			settingMap['initVersion'] = versionumero

			tokenInput = str(input('Syötä bot-token apustajalle: '))
			while ':' not in tokenInput:
				print('\n')
				print('Kokeile uudestaan – bot-token on muotoa "123456789:ABHMeJViB0RHL..."')
				tokenInput = str(input('Syötä bot-token apustajalle: '))

			settingMap['botToken'] = tokenInput

			# OWM API-key
			tokenInput = str(input('Syötä OpenWeatherMap -palvelun API-avaimesi: '))
			settingMap['owmKey'] = tokenInput

			json.dump(settingMap, jsonData, indent=4, sort_keys=True)
			time.sleep(2)
			print('\n')


def updateToken(updateTokens):
	# create /data and /chats
	if not os.path.isdir('data'):
		firstRun()

	if not os.path.isfile('data' + '/botSettings.json'):
		with open('data/botSettings.json', 'w') as jsonData:
			settingMap = {} # empty .json file
	else:
		with open('data' + '/botSettings.json', 'r') as jsonData:
				settingMap = json.load(jsonData) # use old .json

	if 'botToken' in updateTokens:
		tokenInput = str(input('Syötä bot-token apustajalle: '))
		while ':' not in tokenInput:
			print('Kokeile uudestaan – bot-token on muotoa "123456789:ABHMeJViB0RHL..."')
			tokenInput = str(input('Syötä bot-token apustajalle: '))

		settingMap['botToken'] = tokenInput

	if 'owmToken' in updateTokens:
		# OWM API-key
		tokenInput = str(input('Syötä OpenWeatherMap -palvelun API-avaimesi: '))
		settingMap['owmKey'] = tokenInput

	with open('data' + '/botSettings.json', 'w') as jsonData:
		json.dump(settingMap, jsonData, indent=4, sort_keys=True)

	time.sleep(2)
	print('Päivitys onnistui!\n')


def main():
	# some global vars for use in other functions
	global TOKEN, WEATHERKEY, bot, versionumero, botID
	global debugLog, debugMode

	# current version
	versionumero = '1.4.5'

	# default
	start = False
	debugLog = False
	debugMode = False

	# closing stuff
	atexit.register(exitHandler)

	# list of args
	startArgs = ['start', '-start']
	debugArgs = ['log', '-log', 'debug', '-debug']
	botTokenArgs = ['newbottoken', '-newbottoken']
	owmTokenArgs = ['newowmtoken', '-newowmtoken']

	if len(sys.argv) is 1:
		print('Anna ainakin yksi seuraavista argumenteista:')
		print('\tapustaja.py [-start, -newBotToken, -newOWMToken, -log]\n')
		print('Esim: python3 apustaja.py -start')
		print('\t-start käynnistää botin normaalisti')
		print('\t-newBotToken vaihtaa botin käyttöavaimen')
		print('\t-newOWMToken vaihtaa OpenWeatherMapin API-avaimen')
		print('\t-log tallentaa tapahtumat log-tiedostoon\n')
		sys.exit('Ohjelma pysähtyy...')

	else:
		updateTokens = []

		for arg in sys.argv:
			arg = arg.lower()

			if arg in startArgs:
				start = True

			if arg in botTokenArgs:
				updateTokens.append('botToken')
			
			if arg in owmTokenArgs:
				updateTokens.append('owmToken')

			if arg in debugArgs:
				if arg == 'log' or arg == '-log':
					debugLog = True
					if not os.path.isdir('data'):
						firstRun()
					
					log = 'data/log.log'

					# disable logging for urllib and requests because jesus fuck they make a lot of spam
					logging.getLogger("requests").setLevel(logging.WARNING)
					logging.getLogger("urllib3").setLevel(logging.WARNING)
					logging.getLogger("gtts").setLevel(logging.WARNING)
					logging.getLogger("pydub").setLevel(logging.WARNING)
					logging.getLogger('chardet.charsetprober').setLevel(logging.WARNING)

					logging.basicConfig(filename=log,level=logging.DEBUG,format='%(asctime)s %(message)s', datefmt='%d/%m/%Y %H:%M:%S')
					logging.info('🤖 Bot started')

				if arg == 'debug' or arg == '-debug':
					debugMode = True


		if len(updateTokens) is not 0:
			updateToken(updateTokens)

		if start is False:
			sys.exit()

	# if data folder isn't found, we haven't run before (or someone pressed the wrong button)
	if not os.path.isdir('data'):
		firstRun()

	try:
		with open('data' + '/botSettings.json', 'r') as jsonData:
			settingMap = json.load(jsonData)

	except FileNotFoundError:
		firstRun()

		with open('data' + '/botSettings.json', 'r') as jsonData:
			settingMap = json.load(jsonData)

	# token for the Telegram API; get from args or as a text file
	if len(settingMap['botToken']) is 0 or ':' not in settingMap['botToken']:
		firstRun()
	
	else:
		TOKEN = settingMap['botToken']
		WEATHERKEY = settingMap['owmKey']

	# create the bot
	bot = telepot.Bot(TOKEN)

	# handle ssl exceptions
	ssl._create_default_https_context = ssl._create_unverified_context

	# get the bot's specifications
	botSpecs = bot.getMe()
	botUsername = botSpecs['username']
	botID = botSpecs['id']

	# valid commands we monitor for
	global validCommands, validCommandsAlt
	validCommands = ['/markov','/s','/info','/saa','/tuet', '/um', '/settings', '/tts', '/webcam', '/roll', '/start', '/help']
	validCommandsAlt = [] # commands with '@botUsername' appened

	for command in validCommands:
		altCommand = command + '@' + botUsername
		validCommandsAlt.append(altCommand)

	MessageLoop(bot, handle).run_as_thread()
	time.sleep(1)

	if debugMode is False:
		print('| apustaja versio {:s}'.format(versionumero))
		print('| älä sulje tätä ikkunaa tai aseta laitetta lepotilaan. Lopetus: ctrl + c.')
		time.sleep(0.5)

	# run main function, keep the program running.
	if debugMode is False:
		statusMsg = f'✅ yhteys Telegramiin muodostettu - {botUsername} toimii nyt taustalla'
		sys.stdout.write('%s\r' % statusMsg)

	if debugLog is True:
		logging.info('✅ Bot connected')

	# fancy prints so the user can tell that we're actually doing something
	if debugMode is False:
		while True:
			for i in range(1,4):
				repStr = ''
				for n in range(0,i):
					repStr = repStr + '.'

				repStr = statusMsg + repStr
				sys.stdout.write('%s\r' % repStr)
				sys.stdout.flush()
				time.sleep(1)

			for i in range(2,-1,-1):
				subStr = ''
				repStr = '...'
				if i > 0:
					for n in range(0,i):
						subStr = subStr + '.'

				for n in range(0,3-i):
					subStr = subStr + ' '

				repStr = statusMsg + subStr
				sys.stdout.write('%s\r' % repStr)
				sys.stdout.flush()
				time.sleep(1)

	else:
		while True:
			time.sleep(1)

main()
