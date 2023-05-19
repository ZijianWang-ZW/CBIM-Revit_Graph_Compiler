#%%
#--------------------------------------------------------------------------#
#   This file contains a series of functions for constructing/saving a graph from csv
#--------------------------------------------------------------------------#
import rdflib
from rdflib import URIRef, Literal, Namespace
from rdflib.namespace import RDF
import csv
import glob
import os
import trimesh
from uuid import uuid4


bot_ns = Namespace("https://w3id.org/bot#")
revit_ns = Namespace("http://example.org/revitprops#")
fog_ns = Namespace("https://w3id.org/fog#")




#-------------------------------------------------------------------------#
#   This function read csv attribute return a list consisting of 
#   element attribute dictionaries like in Dynamo 
#--------------------------------------------------------------------------#
def ReadAttribute(csv_path, exact_geometry_folder_path):

    with open(csv_path) as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        dict_list = []

        att_dict_temp = {}

        for row in csv_reader:

            if str(row) == "['==========']":
                # append an element's attribute to the list when it is not empty
                if att_dict_temp:
                    dict_list.append(att_dict_temp)
                # reset as empty for the next attribute
                att_dict_temp = {}

            else:
                key = row[0].strip().replace(" ", "") #move heading, tailing, between spaces
                key = key[0].lower() + key[1:]


                if len(row) >= 1  and  len(row) <=3:
                    
                    value = row[1].strip().replace(" ", "")

                    if value == "Yes":
                        value = True 
                    elif value == "No":
                        value = False 

                elif len(row) >3 :
                    
                    value = row[1].split("[")[-1] + "," +  row[2] + "," + row[3].split("]")[0]  

                else:
                    value = ""
                # print(value)
                att_dict_temp[key]=value #put it as an element in the dictionary


    # add bounding box
    # dict_list = AddBBX(dict_list, exact_geometry_folder_path)

    # add "building" object mannually 
    # dict_list = AddBuilding(dict_list)

    # delete HVAC zone (if you need, you can delete this for loop)
    for each in dict_list:

        if each['category'] == 'HVACZones':
            
            dict_list.remove(each)

    return dict_list


#%%
#--------------------------------------------------------------------------#
#   This function polishes the input list of object property dictionary by:
#   1) replace some string values as float, 
#   2) with uniform unit (like mm)
#   3) round float and keep only 1 decimal
#   4) remove unit text
#   5) remove items with 'None' values
#--------------------------------------------------------------------------#

def PolishPropDict(dict_list):
    trans_table = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹°", "0123456789d")
    
    for i, elem_dict in enumerate(dict_list): # loop through each object dict
        for key, value in elem_dict.copy().items(): # loop through each prop/value pair
            
            # In case of ID/option related value, keep as is and continue to next item
            if 'id' in key.lower() or 'option' in key.lower(): continue
            
            # In case of non-string values - continue to next item
            if type(value) is not str: continue
            
            # In case of value contains "None" - remove item from dict and continue to next item
            if 'none' in value.lower():
                dict_list[i].pop(key)
                continue
            
            value = value.translate(trans_table)
            value_new = None
            
            # In case of value is list of number encoded as string - round the numbers and return string
            if ',' in value:
                try:
                    num_list = list(map(float, value.split(', ')))
                    num_list = [round(n, 1) for n in num_list]
                    value_new = ", ".join([str(n) for n in num_list])
                except ValueError: pass
            
            # In case of value is pure number but in string format - convert to rounded float 
            try: value_new = float(round(float(value), 1))
            except ValueError: pass
            
            # In case of value is number with unit - remove unit and convert to rounded float
            if value[-1].lower() == 'm':
                try: value_new = round(float(value[:-1]) * 1e3, 1)
                except ValueError: pass
            elif value[-2:].lower() == 'm2':
                try: value_new = round(float(value[:-2]) * 1e6, 1) 
                except ValueError: pass
            elif value[-2:].lower() == 'm3':
                try: value_new = round(float(value[:-2]) * 1e9, 1)
                except ValueError: pass
            elif value[-1].lower() == 'd':
                try: value_new = round(float(value[:-1]), 1)
                except ValueError: pass
            
            if value_new is not None:
                dict_list[i][key] = value_new
    
    return dict_list


#%% 
#--------------------------------------------------------------------------#
#   This function inputs an dictionary of an element and 
#   creates a node for each element
#--------------------------------------------------------------------------#
def CreatePerNode(g, one_element, node_namespace):
    
    ## construct the element name
    print(one_element['category'])

    
    ele_name = node_namespace  + one_element['category'] + "_" + one_element['uniqueId']
    ele_name = URIRef(ele_name)  #rdflib.term.

    keys = one_element.keys()

    # add attributes for each node 
    for each_key in keys:

        value = one_element[each_key]
        
        if each_key == "bbx":
            link = rdflib.term.URIRef(bot_ns+"hasSimple3DModel")
        else:
            link = rdflib.term.URIRef(revit_ns + each_key)
 
        g.add((ele_name, link, Literal(value)))
    

    # add each node for a type of bot elements
    if one_element["category"] == "Site":
        # g.add((ele_name, RDF.type, bot_ns.Site))
        pass
    elif one_element["category"] == "Building":
        # g.add((ele_name, RDF.type, bot_ns.Building))
        pass
    elif one_element["category"] == "Levels":
        g.add((ele_name, RDF.type, bot_ns.Storey))
    elif one_element["category"] == "HVACZones": # need to improve # we may make errors here
        # g.add((ele_name, RDF.type, bot_ns.Space))
        pass
    else:
        g.add((ele_name, RDF.type, bot_ns.Element))



#--------------------------------------------------------------------------#
#   This function  links two nodes by giving the node name and link name
#--------------------------------------------------------------------------#
def Link2Elemts(g, category1, guid1, category2, guid2, link, node_namespace, link_namespace):

    node1 = node_namespace  + category1 + "_" + guid1
    node1 = rdflib.term.URIRef(node1) 

    node2 = node_namespace  + category2 + "_" + guid2
    node2 = rdflib.term.URIRef(node2)

    link = rdflib.term.URIRef(link_namespace+link)

    g.add((node1, link, node2)) 



#--------------------------------------------------------------------------#
#   This function 
#   1) links all elements to its corresponding levels
#   2) link all levels to an artificial building 
#   3) link the artificial building to the site 
#--------------------------------------------------------------------------#
def LinkLevelBuildingSite(g, att_list, node_namespace): 

    ## 1 link elements to levels
    # there are several situations. 
    # 1) For window, or other BIM elements,
    # they contain the attribute of "Level", easier for linking.
    # 2) But for wall, it does not have the attributes, 
    # but with the attribute "base contraint". 
    # The 2) situation needs to use other information from the attributes
    
    # create a dictionary which has level number and guid
    level_guid_dict = {}

    for one_element in att_list:

        if one_element['category'] == "Levels":

            level_guid_dict[one_element['name']] = one_element['uniqueId']


    # link elements with "Level" attribute
    for one_element in att_list:

        if "level" in one_element.keys():

            level_no = one_element['level']

            if level_no in level_guid_dict.keys():

                level_id = level_guid_dict[level_no]
                level_cat = 'Levels'

                ele_cat = one_element['category']
                ele_id = one_element['uniqueId']

                # create link "containsElement"
                Link2Elemts(g, level_cat, level_id, ele_cat, ele_id, "containsElement", node_namespace, bot_ns)

    # for walls, find out its "base constrains", and link to corresponding levels
    for one_element in att_list:

        if "baseConstraint" in one_element.keys():

            level_no = one_element['baseConstraint']

            if level_no in level_guid_dict.keys():

                level_id = level_guid_dict[level_no]
                level_cat = 'Levels'

                ele_cat = one_element['category']
                ele_id = one_element['uniqueId']

                # create link "containsElement"
                Link2Elemts(g, level_cat, level_id, ele_cat, ele_id, "containsElement", node_namespace, bot_ns)

    # similar for structural beams, "Structural Framing", we link it to "Reference Level"
    for one_element in att_list:

        if "referenceLevel" in one_element.keys():

            level_no = one_element['referenceLevel']

            if level_no in level_guid_dict.keys():

                level_id = level_guid_dict[level_no]
                level_cat = 'Levels'

                ele_cat = one_element['category']
                ele_id = one_element['uniqueId']

                # create link "containsElement"
                Link2Elemts(g, level_cat, level_id, ele_cat, ele_id, "containsElement", node_namespace, bot_ns)


    ## 2 link levels to building
    for one_element in att_list:

        if one_element['category'] == "Building":

            bud_id = one_element['uniqueId']
            bud_cat = one_element['category']

            for each in level_guid_dict:

                level_cat = 'Levels'
                level_id = level_guid_dict[each]

                Link2Elemts(g, bud_cat, bud_id, level_cat, level_id, "hasStorey", node_namespace, bot_ns)

def LinkElementToHost(g, att_list, node_namespace):
    # collect all elements' uniqueID
    ele_uniqueid = []
    ele_id = []
    ele_cat = []

    for each in att_list:

        ele_uniqueid.append(each["uniqueId"])
        ele_id.append(each['id'])
        ele_cat.append(each['category'])

    for each in att_list:

        if ('hostId' in each.keys()) and (each['hostId']!= '-1'): 

            # get the host id and its attributes 
            hostid = each["hostId"]

            temp = ele_id.index(hostid)

            hostuniqueid = ele_uniqueid[temp]

            hostcat = ele_cat[temp]

            objuniqueid = each['uniqueId']
            objcat = each['category']

            Link2Elemts(g, hostcat, hostuniqueid, objcat, objuniqueid, "hasSubElement", node_namespace, bot_ns)






#%%
#--------------------------------------------------------------------------#
#   This function links elements with corresponding exact geometry
#--------------------------------------------------------------------------#
def LinkExactGeometry(g, att_list, exact_geometry_folder_path, node_ns):

    # collect all elements' uniqueID
    ele_uniqueid = []
    ele_id_cat = {}

    for each in att_list:
        unique_id = each["uniqueId"]
        ele_uniqueid.append(unique_id)
        ele_id_cat[unique_id] = each['category']
    
    # collect the unique id from received exact geometry
    eg_list = glob.glob(exact_geometry_folder_path+os.sep+"*.ply")


    for each in eg_list:
        # each present the full path for the exact geometry
        file_uiqueid=os.path.basename(each).split(".ply")[0]

        if file_uiqueid in ele_uniqueid:

            category = ele_id_cat[file_uiqueid]
            
            node1 = node_ns + category + "_" + file_uiqueid
            node1 = rdflib.term.URIRef(node1)

            link = rdflib.term.URIRef(fog_ns+"asPly")

            # print(each)
            g.add((node1, link, Literal(each)))


#%%
#--------------------------------------------------------------------------#
#   This function construct the graph by putting all previous functions together
#--------------------------------------------------------------------------#
def graph_construction(node_ns, csv_file_path, ttl_file_path, exact_geometry_folder_path):

    g = rdflib.Graph() 

    # #%%
    # #### for test
    # csv_file_path = "../database_arc/original backup/attribute_temp.csv"
    # exact_geometry_folder_path = "../database_arc/original backup/"
    # g = rdflib.Graph()
    # node_ns = Namespace("http://example.org/resources/arc/")
    # ttl_file_path = "test.ttl"
    # #### test code end

    # read the csv file and save as dictionary list
    att_list = ReadAttribute(csv_file_path, exact_geometry_folder_path)

    # polish the format of attributes
    att_list = PolishPropDict(att_list)

    g.bind('inst', node_ns)
    g.bind('bot', bot_ns)
    g.bind('rvtprop', revit_ns)
    g.bind('fog', fog_ns)

    # create all nodes
    for each in att_list:
        CreatePerNode(g, each, node_ns)

    # link nodes with levels, link levels to building & building to cite
    # LinkLevelBuildingSite(g, att_list, node_ns)

    # link some element to its host
    LinkElementToHost(g, att_list, node_ns)

    # link with extention layer exact geometry 
    # LinkExactGeometry(g, att_list, exact_geometry_folder_path, node_ns)

    # print(g.serialize())
    g.serialize(destination=ttl_file_path) # "test.ttl"
    # %%




node_ns = rdflib.Namespace('http://example.org/resources/arc/')
csv_file_path = 'attribute_temp.csv'
ttl_file_path = 'apt2_revit_raw.ttl'
exact_geometry_folder_path = ".\exactgeometry"
graph_construction(node_ns, csv_file_path, ttl_file_path, exact_geometry_folder_path)