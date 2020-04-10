

import os
from mycroft.skills.core import MycroftSkill, intent_handler
from mycroft import intent_file_handler
from mycroft.util.log import getLogger
from adapt.intent import IntentBuilder
import asyncio
from ourgroceries import OurGroceries
import datetime
import json


class OurGroceriesSkill(MycroftSkill):
    @intent_handler(IntentBuilder("").require("FindFileKeyword"))
    def __init__(self):
        super(OurGroceriesSkill, self).__init__()
        #self.username = self.settings.get('user')
        #self.password = self.settings.get('password')
        self.username = "groceries"
        self.password = ""
        self.ourgroceries_object = OurGroceries(self.username, self.password)
        self.log.info(self.ourgroceries_object)
        asyncio.run(self.ourgroceries_object.login())
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

        :param full_list:
        :param item_name:
        :param all_categories:
        :param item_category:
        :return:
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
                    # NOTE this is no longer a value backup item because the id of the new object
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

        :param category_name:
        :param all_categories:
        :return:
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

        :param state_file:
        :param current_timestamp:
        :param object_type:
        :return:
        """
        if os.path.isfile(state_file):
            temp_list = json.load(open(state_file))
            try:
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
            self.write_new_list_to_disk(state_file, full_list)
        return full_list

    def fetch_list_and_categories(self, object_type=None):
        """

        :param object_type:
        :return:
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

        :param override:
        :return:
        """
        current_timestamp = self.current_time.timestamp()
        if override is None:
            grocery_list = self.check_file_age(self.grocery_state_file, current_timestamp, object_type="groceries")
            all_categories = self.check_file_age(self.category_state_file, current_timestamp, object_type="categories")
        else:
            grocery_list = self.fetch_list_and_categories(object_type="groceries")
            all_categories = self.fetch_list_and_categories(object_type="categories")
        return grocery_list, all_categories

    @staticmethod
    def return_category_id(category_to_search_for, all_categories):
        """

        :param category_to_search_for:
        :param all_categories:
        :return:
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

        :param message:
        :return:
        """
        category = None
        item_to_add = message.data['Food']
        try:
            category = message.data['Category']
        except KeyError:
            pass
        self.log.info(message.data)
        self.log.info(item_to_add)
        self.speak("Adding %s to your list" % item_to_add)
        all_shopping_list, categories = self.refresh_lists()
        self.add_to_my_list(full_list=all_shopping_list, item_name=item_to_add, all_categories=categories,
                            item_category=category)


def create_skill():
    return OurGroceriesSkill()
