import time
import discogs_client

# Log in to Discogs
discogs_object = discogs_client.Client('m.quinn.moore@mac.com', user_token='uTbNgZKGUTdbApogTFCFDxCnozYOdPUmIeaHmhvo')
discogs_user = discogs_object.identity()

for example_item in discogs_user.collection_folders[1].releases:
    time.sleep(1)

    print(" ")
    print(example_item)
    print(example_item.release.year)

#    master_year = getattr(example_item.release.master, 'year', None)
#    print(master_year)

    if example_item.release.master:
        print(example_item.release.master.year)
        print(example_item.release.master.title)
    else:
        print("No master release")
