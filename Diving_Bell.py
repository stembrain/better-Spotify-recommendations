# -*- coding: utf-8 -*- python3
"""
Created on Sat Feb 29 03:00:39 2020

@author: Antiochian

User interface for this file is provided in "CLI.py", although there are some hidden
debug functions in here that cannot be accessed from the former, which are at the bottom
of this file.

TIMINGS FOR DIFFERENT DISCOVERY METHODS:
Recursive tree:
    20min for ~1000 highly targeted values
Stochastic from chained recc pings:
    8.773 min for 1250 values
Stochastic from SQL loose ends:
    6.963 min for 1250 values
"""

import spotipy
import spotipy.util as util
import time
import sqlite3
import re
import secret_config
from random import shuffle

#production global vars
global NUM_OF_RECCS, ID_LENGTH
NUM_OF_RECCS = 10       #number of branches leading from each artist in the database
ID_LENGTH = 25          #maximum string length of a spotify ID, plus change
global DATA_CEILING
DATA_CEILING = 32768    #maximum number of entries the program is allowed to try to access at a time (prevent memory overflow)
global POP_MIN          
POP_MIN = 20            #maximum popolarity metric required to qualify for inclusion
global FILENAME
FILENAME=r"data/artistdb.db"


################### DEBUGGING VARIABLES #####################

global DEBUGCOUNTER
DEBUGCOUNTER = 0

#test artist ID values for debugging
#PUPseed = '4b2sN5dz0hX8hOZwC3Fckr' #PUP
#SWANSseed = '79S80ZWgVhIPMCHuvl6SkA' #Swans
#BHseed = '56ZTgzPBDge0OvCGgMO3OY' #beach house
#FLseed = '16eRpMNXSQ15wuJoeqguaB' #flaming lips
#slickseed = '1W9qOBYRTfP7HcizWN43G1' #slick rick
#parquetseed = '23NIwARd4vPbxt3wwNnJ6k' #parquet courts

############## SQLITE UTILITIES ###################

def make_database():
    """Make database + table if it doesnt already exist. Does nothing
    if the database already exists, so its harmless (albeit a little 
    unprofessional) to overcall this function"""
    global NUM_OF_RECCS, ID_LENGTH, FILENAME
    execution_string = '''CREATE TABLE IF NOT EXISTS Artists (
                        id varchar('''+str(ID_LENGTH)+''')'''
    for num in range(1,1+NUM_OF_RECCS):
        execution_string += ', recc'+str(num)+' varchar('+str(ID_LENGTH)+')'
    execution_string += " );"
    db = sqlite3.connect(FILENAME)
    cursor = db.cursor()
    cursor.execute(execution_string)
    db.commit()
    db.close()
    return

def insert_rows(db,cursor,list_of_rows):
    """Insert multiple rows at once into SQL table"""
    global NUM_OF_RECCS
    cursor = db.cursor()
    for row in list_of_rows:
        if not exists_in_db(cursor, row[0]): #if DOES NOT EXIST then ADD
            valstring = (",?"*(1+NUM_OF_RECCS))[1:]
            execution_string= '''INSERT INTO Artists
                                VALUES ('''+valstring+''');'''
            cursor.execute(execution_string,tuple(row))
##DEBUG ONLY:
#            #print("\t ",row[0])
#        else:
#           #print("duplicate spotted at SQL: ",row[0]," skipping...") 
    db.commit()
    return

def get_row(target_id):
    """Return row from header ID"""
    db = sqlite3.connect(r"data/artistdb.db")
    cursor=db.cursor()
    execution_string = "SELECT * FROM Artists WHERE id='"+target_id+"'"
    cursor.execute(execution_string)
    row = cursor.fetchone() #potential for a fetchall() here to handle duped IDs bug/issue
    return row

def exists_in_db(cursor, ID):
    """Boolean to check if item exists in "id" column"""
    cond_string = '''SELECT EXISTS(SELECT 1 FROM Artists WHERE id = '''+"'"+str(ID)+"')"
    cursor.execute(cond_string)
    return cursor.fetchone()[0]

def cross_columnar_search(target,db=None,cursor=None):
    """Search to see where the target ID features in at least one column that ISNT the "id" one """
    if db==None:
        db = sqlite3.connect(r"data/artistdb.db")
        cursor=db.cursor()
    cursor.execute('SELECT * from Artists')   
    column_names = list(map(lambda x: x[0], cursor.description))
    search_string = ''' SELECT id FROM Artists WHERE '''+column_names[1]+"='"+target+"'"
    for col in column_names[2:]:
        search_string += " OR "+col+ "='"+target+"'"
    cursor.execute(search_string)
    results = [el[0] for el in cursor.fetchall()]
    return results
    
############### SPOTIFY API UTILITIES #################

def setup():
    """Set up API connection to spotify using the config file supplied"""
    CLIENT_ID, CLIENT_SECRET,REDIRECT, USER_NAME = secret_config.get_spotify_info()
    scope = 'user-library-read playlist-modify-private'
    token = util.prompt_for_user_token(USER_NAME, scope,CLIENT_ID,CLIENT_SECRET,REDIRECT)
    spotify = spotipy.Spotify(auth=token)
    return spotify

def recc_from_ID(spotify, target_artist,LIMIT=20):
    """Get spotifys reccs from a target artist ID"""
    spotify = setup()
    recc_dict = spotify.artist_related_artists(target_artist)
    return {el['id'] for el in recc_dict['artists'][:LIMIT]} # AS A SET
 

def CL_search(spotify, search_term):
    """Quick method to find an artist's ID using the inbuilt spotify search feature"""
    results = spotify.search(q=search_term, type='artist',limit=10) #"album"+
    index = 1
    opt_dict = {}
    for item in results['artists']['items']:
        name = item['name']
        all_genres = item['genres']
        if len(all_genres):
            genre = all_genres[0]
        else:
            genre = "unknown"
        track_id = item['id']
        opt_dict[index] = track_id
        print("\t",index,": ",name," - ",genre )
        index +=1
    choice = input("Enter choice (Q to cancel): ")
    if choice.lower() != "q":
        return opt_dict[int(choice)] #ID value of choice
    else:
        return 0 
    
    
############# DATABASE SCRAPERS #################

       
def breadthwise_launcher(start_ID,batches=1,maxdepth=1):   
    """This launches a recursive function (below) that spreads tree-like from a 
    source. Is slow, but has the advantage that it adds very similar artists,
    effective for targeting growth towards a specific niche or genre"""
    spotify = setup()
    db = sqlite3.connect(FILENAME)
    cursor = db.cursor() 
    
    execution_string = "SELECT * FROM Artists"
    cursor.execute(execution_string)
    row = cursor.fetchall() #all IDS
    master_completed = set([el[0] for el in row]) #fill completed with all current IDs
    recc_seeds = list(recc_from_ID(spotify,start_ID,batches))
    for i in range(batches):
        seedname = ID_list_to_string(spotify,[start_ID],1)[0]
        print("\nBatch #",i+1,", SEED: ",seedname)
        print("\tProg: ",end="")
        master_completed.update(breadthwise_scraper(spotify,db,cursor, start_ID, master_completed, 0, maxdepth))
        db.commit()
        start_ID = recc_seeds[i]
    db.close()
    global DEBUGCOUNTER
    print("\n",DEBUGCOUNTER," new entries")
    return

def breadthwise_scraper(spotify,db,cursor, curr_ID, completed, depth, depth_limit):
    """ total count = depth * num of reccs """
    global DEBUGCOUNTER #debug: keep track of how many tracks are being added/how fast
    if depth > depth_limit:
        return completed
    new_row = get_row(curr_ID)
    if new_row == None:
        new_row = [[curr_ID] + list(recc_from_ID(spotify, curr_ID, NUM_OF_RECCS))]
    else:
        new_row = [list(new_row)]
    if curr_ID not in completed and len(new_row[0]) == NUM_OF_RECCS+1:
        insert_rows(db,cursor,new_row)
        DEBUGCOUNTER +=1
    completed.update(set([curr_ID]))
    depth += 1
    if depth == 1:
        for ID in new_row[0][1:]:
            breadthwise_scraper(spotify,db,cursor, ID, completed, depth, depth_limit)
            print("#",end='')
    else:
        for ID in new_row[0][1:]:
            breadthwise_scraper(spotify,db,cursor, ID, completed, depth, depth_limit)
    return completed

def stochastic_launcher(max_count,incompletes=set([])):
    """This method instead scans the database for any 'loose ends', IDs that point nowhere,
    and fills them out. This is much faster than above, but is a lot more "scattershot" and
    undirected.
    It is fast enough to be limited by the spotify rate limiter so any
    further optimisation, while possible, would be pointless."""
    spotify = setup()
    db = sqlite3.connect(r"data/artistdb.db")
    cursor=db.cursor()
    
    execution_string = "SELECT * FROM Artists"
    cursor.execute(execution_string)
    row = cursor.fetchall() #all IDS
    master_completed = set([el[0] for el in row]) #fill completed with all current IDs
    master_completed.update(incompletes)
    recent_IDs = [el[1:] for el in row] #limit row here to prevent a memory overflow?
    queue = set([ID for sublist in recent_IDs for ID in sublist])
    queue = queue - master_completed
    count = 0
    while count < max_count:
        target_ID = queue.pop()
        while target_ID in master_completed:
            try:
                target_ID = queue.pop()
            except KeyError: #queue empty
                print("Queue emptied! Refilling...")
                cursor.execute(execution_string)
                row = cursor.fetchall() #all IDS
                recent_IDs = [el[1:] for el in row] #limit row here to prevent a memory overflow?
                queue = set([ID for sublist in recent_IDs for ID in sublist])
                queue = queue - master_completed
        #print(ID_list_to_string(spotify,[target_ID],1)[0])
        master_completed.update(stochastic_scraper(spotify,db,cursor,target_ID,master_completed))
        cursor.execute("SELECT id FROM Artists")
        row = [el[0] for el in cursor.fetchall()] #potential for a fetchall() here to handle duped IDs bug/issue
        queue.update(set(row[1:]))                
        count += 1    
    db.commit()
    cursor.execute(execution_string)
    row = cursor.fetchall() #all IDS
    database_IDs = set([ID for sublist in row for ID in sublist])
    incompletes = master_completed - database_IDs
    db.close()
    return incompletes

def stochastic_scraper(spotify,db,cursor,curr_ID,master_completed=set([])):
    new_row = [curr_ID] + list(recc_from_ID(spotify, curr_ID, NUM_OF_RECCS))
    if len(new_row) != NUM_OF_RECCS+1:
        print("Incomplete links for artist ID#:",curr_ID,", skipping...")
    else:
        insert_rows(db,cursor,[new_row])
    return set(new_row) #still add to completed though, dont want to repeat the waste of time

############ DATABASE GROWTH FUNCTIONS ###############
    
def targeted_scraper(width=5,depth=2,targetseed=None):
    """This scraper is much slower, and more wasteful on the API, but is
    extremely targetted towards a specific artist, and never strays too far away from it.
    Best used in small doses.
    """
    spotify=setup()
    if targetseed==None:
        targetseed=CL_search(spotify,input("Artist Search: "))
    print("Running ",width,"x",depth," search...")
    print("[Estimated runtime = ",round((NUM_OF_RECCS**depth)*width*0.025/60,3)," minutes]") #84 is experimentally determined
    t0 = time.time()
    breadthwise_launcher(targetseed,width,depth)
    estimate_database_size()
    print("\tCompleted in: ",round((time.time()-t0)/60,3)," min")
    return

def idle_scraper():
    """This scraper is fast, minimizes Spotify API calls, and can be run indefinitely
    However it only produces very loosely-grouped results, and can stray off into
    incredibly niche artists if left unchecked. To mitigate this it resets after 1250
    additions, but its still a concern"""
    batch_num = 0
    incompletes = set([])
    while True:
        batch_num += 1
        t0 = time.time()
        print("\nBATCH #",batch_num,":")
        incompletes = stochastic_launcher(1250,incompletes)  
        print("\tCompleted in: ",round((time.time()-t0)/60,3)," min")
        print(int(len(incompletes))," incompletes found")
        estimate_database_size()

def default_reccs(spotify,target,limit=False):
    global NUM_OF_RECCS
    """Get spotifys default recommendations (for comparison)"""
    row = get_row(target)
    if row == None:
        #manually search if not in database already
        print("Not found in database. Pinging Spotify...")
        row =list(recc_from_ID(spotify, target,NUM_OF_RECCS))
        db = sqlite3.connect(r"data/artistdb.db")
        cursor = db.cursor()
        insert_rows(db,cursor,[ [target] + row]) #surreptitiously add into db for next time
        print("Database Updated")
        db.close()
    matches = row[1:]
    if limit:
        matches = matches[:limit]
    return matches

def reverse_reccs(spotify,target,limit=False):
    """ My own reversed-recommendation system"""
    matches = cross_columnar_search(target)
    if limit:
        matches = matches[:limit]
    return matches

def artists_to_tracks(spotify,artist_list):
    track_list = []
    for artist in artist_list:
        top_tracks = spotify.artist_top_tracks(artist)['tracks']
        shuffle(top_tracks) #randomize
        track_list.append(top_tracks[0])
    return track_list

############# DATABASE DEBUG/ACCESS TOOLS ####################
def estimate_database_size():
    global NUM_OF_RECCS, ID_LENGTH,FILENAME
    row_size = NUM_OF_RECCS*ID_LENGTH
    #get number of rows
    count_string = '''SELECT COUNT(*) FROM Artists'''
    db = sqlite3.connect(FILENAME)
    cursor = db.cursor()
    cursor.execute(count_string)
    number_of_rows = cursor.fetchone()[0]
    db.commit()
    db.close()
    print(number_of_rows," rows, ~",round(row_size*number_of_rows/1000,4),"KB")
    return

def ID_list_to_string(spotify,ID_list, limit=10):
    RATE_LIMIT = 20
    list_length = min(len(ID_list),limit)
    total_batches = list_length//RATE_LIMIT
    remainder = list_length%RATE_LIMIT
    artists = []
    for batch in range(total_batches):
        artists += spotify.artists(ID_list[batch*RATE_LIMIT:(batch+1)*RATE_LIMIT])['artists']
    if remainder:
        artists += spotify.artists(ID_list[total_batches*RATE_LIMIT:total_batches*RATE_LIMIT+remainder])['artists']
    string_list = []
    for item in artists:
        all_genres = item['genres']
        if len(all_genres):
            genre = all_genres[0]
        else:
            genre = "unknown"
        string_list.append(item['name'] + " - " + genre)
    string_list.sort()
    return string_list
    
def print_tracknames(limit=100):
    global FILENAME
     #lower limit for albums, worryingly
    """prints contents of the SQL directory, sorted by Artist - Album"""
    spotify = setup()
    db = sqlite3.connect(FILENAME)
    cursor = db.cursor()
    search_string = ''' SELECT id FROM Artists'''
    cursor.execute(search_string)
    ID_list = [el[0] for el in cursor.fetchall()]
    #implement a 50-buffer system to get around rate limit
    string_list = ID_list_to_string(spotify,ID_list, limit)
    db.close()
    return string_list
    

def dump_all(limit=DATA_CEILING):
    """Lists the names of the first 'limit' items in the database.
    Was a useful debug tool in the early days, now is prohibitively slow due to the size of the DB"""
    string_list = print_tracknames(limit)
    print(*string_list, sep='\n')
    return

def dump_from_regex(search_term):
    """Prohibitively slow way of searching for a regex string in an artists name
    only really useful if you REALLY cant remember an artists name and you REALLY
    need to see if they are on the database for some reason
    """
    global DATA_CEILING
    t0 = time.time()
    string_list = print_tracknames(DATA_CEILING)
    matches = 0
    for item in string_list:
        if re.search(search_term,item):
            print(item)
            matches += 1
    print("\t",matches," found in ",round(time.time()-t0,4)," seconds")
    return

def count_loose_ends():
    global FILENAME
    db = sqlite3.connect(FILENAME)
    cursor = db.cursor()
    cursor.execute('''SELECT * FROM Artists''')
    row = cursor.fetchall() #all IDS
    pointing_IDs = [el[1:] for el in row] #limit row here to prevent a memory overflow?
    header_IDs = [el[0] for el in row]
    header_IDs = set(header_IDs)
    pointing_IDs = set([ID for sublist in pointing_IDs for ID in sublist])
    loose_ends = header_IDs - pointing_IDs
    print(len(loose_ends),"/",len(pointing_IDs)," Loose ends remain")
    db.close()
    return
