import time
import discogs_client
import inspect

# Log in to Discogs
discogs_object = discogs_client.Client('m.quinn.moore@mac.com', user_token='uTbNgZKGUTdbApogTFCFDxCnozYOdPUmIeaHmhvo')
discogs_user = discogs_object.identity()
print(f"Logged into Discogs as {discogs_user}.")



#for example_folder in discogs_user.collection_folders:
#    print(example_folder)

#print(len(discogs_user.collection_folders))

#print(discogs_user.collection_folders[0].name)
#print(discogs_user.collection_folders[1].name)
#print(discogs_user.collection_folders[2].name)

#exit()

print("")
#print("Can we find a full Released field?")

try_count = 0

for example_item in discogs_user.collection_folders[1].releases:
    time.sleep(1)
    example_title = example_item.release.title
    example_artist = example_item.release.artists
    example_artist_idx0 = example_item.release.artists[0]
    example_artist_idx0_profile = example_item.release.artists[0].profile
    example_artist_full_info = discogs_object.artist(example_artist_idx0.id)

#    example_master_id = example_item.release.master
#    example_master = discogs_object.master(example_master_id)

    try_count += 1

    print(" ")
#    print(dir(example_master.release))
    print(example_item)
    print(example_item.release.year)
#    print(example_item.release.title)
#    print(example_item.release.year)
    print(example_item.release.master)
#    print(example_item.release.master.id)
    example_master = discogs_object.release(example_item.release.master)
    print(dir(example_master))
#    print(example_master.year)
#    print(dir(example_master))
#    print(example_master.year)
#    print(example_master.year)


#    exit()

#    print(f"Checking '{example_title}' by {example_artist_idx0.name}")

 #   full_released_date = example_item.release.data.get("released")

  #  if full_released_date:
   #     print(f"Found one for '{example_item.title}' by {example_artist_idx0}")
    #    print(full_released_date)

'''
    print(" ")
#    print("A CollectionItemInstance:")
#    print(example_item)
    print("An Artist:")
    print(dir(example_item.release.artists[0]))


#    print(example_item.release.artists)
#    print(example_item.release.artists[0].id)
#    print(example_item.release.artists[0].name)
#    print(example_item.release.artists[0].groups)


    if hasattr(example_artist_full_info, 'members') and example_artist_full_info.members:
        print(f"...is a group with members: {[m.name for m in example_artist_full_info.members]}")
    else:
        print("...seems to be a solo artist.")



    # Solo indicators
    solo_keywords = [
        'solo artist', 'singer-songwriter', 'born', 'real name',
        'stage name', 'pseudonym', 'moniker'
    ]

    # Group indicators
    group_keywords = [
        'band', 'group', 'duo', 'trio', 'quartet', 'quintet',
        'ensemble', 'orchestra', 'collective', 'crew', 'formation',
        'members', 'lineup', 'consisted of', 'formed by'
    ]

    # Check for solo indicators
    for keyword in solo_keywords:
        if keyword in example_artist_idx0_profile:
            print("solo")

    # Check for group indicators
    for keyword in group_keywords:
        if keyword in example_artist_idx0_profile:
            print("group")





#print("")
#print("A Release:")
#print(dir(example_item.release))
#print("")
#print(example_item.release.__dict__)

    #print(try_count)

exit()


#print("")
#print("A Year:")
#print(dir(example_item.release.year))
#print(example_item.release.year)

print("")
print("Release Data:")
print(dir(example_item.release.data))
#print(example_item.release.year)



print("")
print("An Artist:")
print(dir(example_item.release.artists))
print(example_item.release.artists)

print("")
print("A Title:")
print(dir(example_item.release.title))
print(example_item.release.title)

print("")
print("An Artist list and the first & second indexed Artists:")
print(example_artist)
print(dir(example_artist_idx0))
print(len(example_artist))
print(example_artist_idx0.name)
#print(example_artist_idx1.name)

for next_item in discogs_user.collection_folders[0].releases:
    if len(next_item.release.artists) != 1:
        print(f"Title: {next_item.release.title} Num Artists: {len(next_item.release.artists)} Prime Artist: {next_item.release.artists[0].name}")
    time.sleep(1)


'''
