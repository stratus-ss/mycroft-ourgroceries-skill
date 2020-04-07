import asyncio
from ourgroceries import OurGroceries
import datetime
import json
import os

USERNAME = "groceries"
PASSWORD = ""
OG = OurGroceries(USERNAME, PASSWORD)
asyncio.run(OG.login())
MY_LIST_ID = "a1kD7kvcMPnzr9del8XMFc"
CURRENT_TIME = datetime.datetime.now()
TIME_HEADING_IN_DICT = 'refresh_date'
GROCERY_STATE_FILE = "ourgroceries.txt"
CATEGORY_STATE_FILE = "categories.txt"
bla = asyncio.run(OG.get_my_lists())
for shopping_list in bla['shoppingLists']:
    print(shopping_list['name'])
print("")

def fetch_list_and_categories(object_type=None):
    if object_type == "groceries":
        list_to_return = asyncio.run(OG.get_list_items(list_id=MY_LIST_ID))
    elif object_type == "categories":
        list_to_return = asyncio.run(OG.get_category_items())
    else:
        list_to_return = None
    return (list_to_return)


def write_new_list_to_disk(state_file, new_list):
    with open(state_file, 'w') as f:
        json.dump(new_list, f)


def check_file_age(state_file, current_timestamp, object_type=None):
    if os.path.isfile(state_file):
        temp_list = json.load(open(state_file))
        try:
            last_refresh = temp_list[TIME_HEADING_IN_DICT]
            minutes_since_last_refresh = round((current_timestamp - last_refresh) / 60)
        except KeyError:
            pass
        if minutes_since_last_refresh > 10:
            print("Updating %s list as it is older than 10 minutes" % object_type)
            full_list = fetch_list_and_categories(object_type=object_type)
            full_list[TIME_HEADING_IN_DICT] = current_timestamp
            write_new_list_to_disk(state_file, full_list)
        else:
            print("%s list under 10 minutes old... skipping refresh" % object_type)
            full_list = temp_list
    else:
        full_list = fetch_list_and_categories(object_type=object_type)
        full_list[TIME_HEADING_IN_DICT] = current_timestamp
        write_new_list_to_disk(state_file, full_list)
    return(full_list)


def refresh_lists(override=None):
    current_timestamp = CURRENT_TIME.timestamp()
    if override is None:
        grocery_list = check_file_age(GROCERY_STATE_FILE, current_timestamp, object_type="groceries")
        all_categories = check_file_age(CATEGORY_STATE_FILE, current_timestamp, object_type="categories")
    else:
        grocery_list = fetch_list_and_categories(object_type="groceries")
        all_categories = fetch_list_and_categories(object_type="categories")
    return(grocery_list, all_categories)


def return_category_id(category_to_search_for, all_categories):
    category_to_search_for_lower = category_to_search_for.lower()
    category_id = None
    if len(all_categories['list']['items']) is not 0:
        for category_heading in all_categories['list']['items']:
            # Split the heading because if there is already a duplicate it
            # presents as "{{item}} (2)"
            category_heading_lowered = category_heading['value'].lower().split()[0]
            if category_to_search_for_lower == category_heading_lowered:
                category_id = category_heading['id']
                break
            # attempt to compensate for plurals in categories
            elif category_to_search_for_lower + 's' == category_heading_lowered:
                category_id = category_heading['id']
                break
            elif category_to_search_for_lower + 'ies' == category_heading_lowered:
                category_id = category_heading['id']
                break
            # If we assume that the last character is a plural 'S', slice it off
            # and check to see if the heading is the same
            elif category_to_search_for_lower[:-1] == category_heading_lowered:
                category_id = category_heading['id']
                break
            # Assume the last 3 characters are 'ies' and remove them
            elif category_to_search_for_lower[:-3] == category_heading_lowered:
                category_id = category_heading['id']
                break
    return(category_id)


def add_to_my_list(full_list, item_name, all_categories, category="uncategorized"):
    # check to make sure the object doesn't exist
    # The groceries live in my_full_list['list']['items']
    # Start with the assumption that the food does not exist
    food_exists = False
    toggle_crossed_off = False
    category_lowered = category.lower()
    for food_item in full_list['list']['items']:
        if item_name in food_item['value']:
            print("Already exists")
            try:
                if food_item['crossedOff']:
                    print("Returning crossed off item to list")
                    existing_item_id = food_item['id']
                    toggle_crossed_off = True
            except KeyError:
                pass
            food_exists = True
    if not food_exists:
        category_id = return_category_id(category_lowered, all_categories)
        asyncio.run(OG.add_item_to_list(MY_LIST_ID, item_name, category_id))
        print("Added item")
    else:
        if toggle_crossed_off:
            asyncio.run(OG.toggle_item_crossed_off(MY_LIST_ID, existing_item_id, cross_off=False))


def add_category(category_name, all_categories):
    category_id = return_category_id(category_name, all_categories)
    if category_id is None:
        asyncio.run(OG.create_category(category_name))
        refresh_lists()
        print("Added Category")
    else:
        print("Category already exists")


def uncross_all_items(full_list):
    for food_item in full_list['list']['items']:
        try:
            if food_item['crossedOff']:
                print("Returning %s to list" % food_item['value'])
                asyncio.run(OG.toggle_item_crossed_off(MY_LIST_ID, food_item['id'], cross_off=False))
        except KeyError:
            pass

my_full_list, current_categories = refresh_lists(override=True)

#add_category("Funnies-1ups", current_categories)

# Need to refresh the list if you are going to add an item to a newly created list
#add_to_my_list(my_full_list, "comsics2", current_categories, category="Funnies-onesies")

uncross_all_items(my_full_list)
