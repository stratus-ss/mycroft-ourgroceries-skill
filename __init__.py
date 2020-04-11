

import os
from mycroft.skills.core import MycroftSkill, intent_handler
from mycroft.skills.context import adds_context, removes_context
from mycroft import intent_file_handler
from mycroft.util.log import getLogger
from adapt.intent import IntentBuilder
import asyncio
from ourgroceries import OurGroceries
import datetime
import json


class OurGroceriesSkill(MycroftSkill):
    def __init__(self):
        MycroftSkill.__init__(self)
        #self.username = self.settings.get('user')
        #self.password = self.settings.get('password')
        self.username = "groceries"
        self.password = ""
        # this variable is needed if adding new shopping lists
        self.new_shopping_list_name = ''
        self.ourgroceries_object = OurGroceries(self.username, self.password)
        asyncio.run(self.ourgroceries_object.login())

        # The default list... This should go in the settings.json
        self.default_list_name = "ShOpping LIst"
        self.log.info(self.default_list_name)
        temp_list = asyncio.run(self.ourgroceries_object.get_my_lists())
        for shopping_list in temp_list['shoppingLists']:
            if self.default_list_name.lower() == shopping_list['name'].lower():
                self.my_list_id = shopping_list['id']
                break
        self.current_time = datetime.datetime.now()
        self.time_heading_in_dict = 'refresh_date'
        self.grocery_state_file = "ourgroceries.txt"
        self.category_state_file = "categories.txt"

    def add_to_my_list(self, full_list, item_name, all_categories, item_category="None"):
        """
        This deals with adding items to the active list. This means that objects that
        are being added which are in the crossed-off list will go back to their original
        category.
        A text file is created with a timestamp that is used a cache so as to not
        call out to the internet every time. When a new item is added to a list at
        OurGroceries, it is also added to the text file to help avoid duplicate entries
        :param full_list: (dict) the list received from OurGroceries (dict)
        :param item_name: (string) the name of the item to be added to the list
        :param all_categories: (dict) all the categories currently defined at OurGroceries
        :param item_category: (string) This is the category to add a new item to
        :return: Nothing
        """
        # check to make sure the object doesn't exist
        # The groceries live in my_full_list['list']['items']
        # Start with the assumption that the food does not exist
        food_exists = False
        move_food_between_categories = False
        toggle_crossed_off = False
        if item_category:
            category_lowered = item_category.lower()
        else:
            category_lowered = item_category
        category_id = self.return_category_id(category_lowered, all_categories)
        # basic structure is {'list':{'items':['id': '','value':'','categoryId':'']}}
        for food_item in full_list['list']['items']:
            if item_name in food_item['value']:
                # if the food exists check to see if it is in category the user requested
                try:
                    if category_id == food_item['categoryId']:
                        self.log.info("-----> Already exists in Category")
                        food_exists = True
                    else:
                        move_food_between_categories = True
                except KeyError:
                    # KeyError is likely to happen when an item is uncategorized so assume we should move it
                    self.log.info("---------> Item already exists")
                    move_food_between_categories = True
                    pass
                try:
                    # It is possible that the food exists in the list but its just crossed off
                    # assume that the user wants to toggle it back to the main list
                    if food_item['crossedOff']:
                        print("Returning crossed off item to list")
                        existing_item_id = food_item['id']
                        toggle_crossed_off = True
                except KeyError:
                    pass
        if not food_exists or move_food_between_categories:
            asyncio.run(self.ourgroceries_object.add_item_to_list(self.my_list_id, item_name, category_id))
            self.log.info("-----> Added item <------")
            # update local dict so we dont have to refresh it
            index = 0
            for item in full_list['list']['items']:
                if item_name in item['value']:
                    # NOTE this is no longer a valid backup item because the id of the new object
                    # was not retrieved from the server. This is simply to make sure we dont add duplicates
                    # We are trying to avoid excessive calls to the ourgroceries servers
                    full_list['list']['items'][index] = {'value': item_name, 'categoryId': category_id}
                index += 1
            self.write_new_list_to_disk(self.grocery_state_file, full_list)
        else:
            if toggle_crossed_off:
                asyncio.run(self.ourgroceries_object.toggle_item_crossed_off(self.my_list_id, existing_item_id,
                                                                             cross_off=False))

    def add_category(self, category_name, all_categories):
        """
        This runs the asyncio command to create a new category
        :param category_name: (string) the value of the category to add
        :param all_categories: (dict) the list of all categories
        :return: nothing
        """
        category_id = self.return_category_id(category_name, all_categories)
        if category_id is None:
            asyncio.run(self.ourgroceries_object.create_category(category_name))
            self.refresh_lists()
            print("Added Category")
        else:
            print("Category already exists")

    def check_file_age(self, state_file, current_timestamp, object_type=None):
        """
        This checks a state file on dist for a time stamp. If the timestamp in the file
        is older than minutes_since_last_refresh, a new copy is fetched from OutGroceries
        :param state_file: (string) the state file is either the category dict or the grocery item dict
        :param current_timestamp: (timestamp) the current time/date converted to a time stamp
        :param object_type: (string) either groceries or categories
        :return: the current list retrieved from OurGroceries
        """
        # make sure the file exists before trying to load it
        if os.path.isfile(state_file):
            temp_list = json.load(open(state_file))
            try:
                # check for the time stamp in the dict as this is a value I am adding
                # ignore a KeyError, because that likely means the file has been
                # refreshed from OurGroceries
                last_refresh = temp_list[self.time_heading_in_dict]
                minutes_since_last_refresh = round((current_timestamp - last_refresh) / 60)
            except KeyError:
                pass
            self.log.info("List is %s minutes old" % minutes_since_last_refresh)
            if minutes_since_last_refresh > 10:
                print("Updating %s list as it is older than 10 minutes" % object_type)
                full_list = self.fetch_list_and_categories(object_type=object_type)
                full_list[self.time_heading_in_dict] = current_timestamp
                self.write_new_list_to_disk(state_file, full_list)
            else:
                print("%s list under 10 minutes old... skipping refresh" % object_type)
                full_list = temp_list
        else:
            full_list = self.fetch_list_and_categories(object_type=object_type)
            full_list[self.time_heading_in_dict] = current_timestamp
            # Write the cached file to disk
            self.write_new_list_to_disk(state_file, full_list)
        return full_list

    def fetch_list_and_categories(self, object_type=None):
        """
        Runs the async command to fetch the most recent lists
        :param object_type: (string) either groveries or category
        :return: either the grocery or category list
        """
        if object_type == "groceries":
            list_to_return = asyncio.run(self.ourgroceries_object.get_list_items(list_id=self.my_list_id))
        elif object_type == "categories":
            list_to_return = asyncio.run(self.ourgroceries_object.get_category_items())
        else:
            list_to_return = None
        return list_to_return

    def refresh_lists(self, override=None):
        """
        This is responsible for calling the age check on grocery and category lists
        :param override: (bool) This option will force a new file to be fetched regardless of the time stamp
        :return: both the grocery list and all the categories
        """
        current_timestamp = self.current_time.timestamp()
        if override is None:
            grocery_list = self.check_file_age(self.grocery_state_file, current_timestamp, object_type="groceries")
            all_categories = self.check_file_age(self.category_state_file, current_timestamp, object_type="categories")
        # Skip the age check if the override is passed in
        else:
            grocery_list = self.fetch_list_and_categories(object_type="groceries")
            all_categories = self.fetch_list_and_categories(object_type="categories")
        return grocery_list, all_categories

    @staticmethod
    def return_category_id(category_to_search_for, all_categories):
        """
        This gets the category_id. The category is passed in as a string and needs to
        be converted into an ID. In addition this function attempts to guess at common
        plural endings assuming that if a plural group exists we should add the object
        there
        :param category_to_search_for: this is a string
        :param all_categories: a dict of all the categories
        :return: category id
        """
        try:
            category_to_search_for_lower = category_to_search_for.lower()
        except AttributeError:
            category_to_search_for_lower = category_to_search_for
        category_id = None
        if len(all_categories['list']['items']) is not 0:
            for category_heading in all_categories['list']['items']:
                # Split the heading because if there is already a duplicate it
                # presents as "{{item}} (2)"
                category_heading_lowered = category_heading['value'].lower().split()[0]
                if category_to_search_for_lower is not None:
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
                else:
                    category_id = category_to_search_for
        return category_id

    def uncross_all_items(self, full_list):
        """

        :param full_list:
        :return:
        """
        for food_item in full_list['list']['items']:
            try:
                if food_item['crossedOff']:
                    print("Returning %s to list" % food_item['value'])
                    asyncio.run(self.ourgroceries_object.toggle_item_crossed_off(self.my_list_id,
                                                                                 food_item['id'], cross_off=False))
            except KeyError:
                pass

    @staticmethod
    def write_new_list_to_disk(state_file, new_list):
        with open(state_file, 'w') as f:
            json.dump(new_list, f)

    def stop(self):
        pass

    @intent_handler(IntentBuilder('').require('CreateItemKeyword').require("Food").optionally("Category"))
    def create_item_on_list(self, message):
        """
        I NEED TO FIX THE REGEX AS IT DOES NOT CAPTURE SPACES
        Handles the initial voice interaction from the user.
        Uses add.item.rx and optionally category.rx

        :param message:
        :return:
        """
        category = None
        item_to_add = message.data['Food']
        try:
            category = message.data['Category']
        except KeyError:
            pass
        self.speak("Adding %s to your list" % item_to_add)
        all_shopping_list, categories = self.refresh_lists()
        self.add_to_my_list(full_list=all_shopping_list, item_name=item_to_add, all_categories=categories,
                            item_category=category)

    @intent_handler(IntentBuilder('').require('CreateCategoryKeyword').require("Category"))
    def create_category(self, message):
        """
        This creates the category when invoked by the user
        Uses category.rx
        :param message:
        :return:
        """
        user_entered_category = message.data['Category']
        self.log.info(message.data)
        self.speak("Adding the category %s to your list" % user_entered_category)
        shopping_list, categories = self.refresh_lists(override=True)
        self.add_category(user_entered_category, categories)

    @intent_handler(IntentBuilder('CreateShoppingIntent').require('CreateShoppingListKeyword').require("ListName"))
    @adds_context("CreateAnywaysContext")
    def create_shopping_list(self, message):
        """
        This is an context-aware method that searches for shopping lists of similar names
        and prompts the user before adding a similar category
        Uses add.shopping.list.rx
        Uses do.add.response.dialog
        Relies on either handle_dont_create_anyways_context() or handle_create_anyways_context()
        :param message:
        :return:
        """
        self.new_shopping_list_name = message.data['ListName'].lower()
        current_lists = asyncio.run(self.ourgroceries_object.get_my_lists())
        for current_shopping_list in current_lists['shoppingLists']:
            try:
                current_shopping_list = current_shopping_list['name'].lower()
                if self.new_shopping_list_name in current_shopping_list:
                    if self.new_shopping_list_name == current_shopping_list:
                        self.speak("The shopping list %s already exists" % self.new_shopping_list_name )
                        break
                    else:
                        self.speak("I found a similar naming list called %s" % current_shopping_list)
                        # This hands off to either handle_dont_create_anyways_context or handle_create_anyways_context
                        # to make a context aware decision
                        self.speak("Would you like me to add your new list anyways?", expect_response=True)
                        break
            except AttributeError:
                pass
        # If it gets this far, assume its time to create the list
        asyncio.run(self.ourgroceries_object.create_list(self.new_shopping_list_name ))
        self.speak_dialog('do.add.response')

    @intent_handler(IntentBuilder('DoNotAddIntent').require("NoKeyword").require('CreateAnywaysContext').build())
    @removes_context("CreateAnywayscontext")
    def handle_dont_create_anyways_context(self):
        """
        Does nothing but acknowledges the user does not wish to proceed
        Uses dont.add.response.dialog
        :return:
        """
        self.speak_dialog('dont.add.response')

    @intent_handler(IntentBuilder('AddAnywaysIntent').require("YesKeyword").require('CreateAnywaysContext').build())
    @removes_context("CreateAnywayscontext")
    def handle_create_anyways_context(self):
        """
        If the user wants to create a similarly named list, it is handled here
        Uses do.add.response.dialog
        :return:
        """
        self.speak_dialog('do.add.response')
        asyncio.run(self.ourgroceries_object.create_list(self.new_shopping_list_name ))

    def stop(self):
        pass


def create_skill():
    return OurGroceriesSkill()
