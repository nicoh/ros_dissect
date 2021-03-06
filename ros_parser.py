#!/usr/bin/python

import rospkg
import roslib
import sys
import re
import os
import string

CATEGORIES = ['sub', 'pub', 'srv', 'srv_called', 'param', 'param_set', 
        'req_tf', 'prov_tf', 'goal', 'feedback', 'result', 'act_called']

CAT_5C = ['comm', "conf", "coord", "comput", "compo"] # Red, Blue, Green, Grey, Yellow

DEFAULT_ORDER = ['name', 'type', 'from', 'to', 'desc', 'default']

GENERIC = '<([^>]*)>'   # <something>
QSTRING = '"([^"]*)"'
PSTRING = '["\']([^"\']*)["\']'   # not quite right, will break on "can't"
NEXT_PARAM =  ',\s*([^\,]+)' # , something, 
FINAL_PARAM = ',\s*([^\)]+)\)' # , something)


PATTERNS = [
#[CATEGORY,     PATTERN,                                            FIELD_LIST], 
# Add empty patterns () for blank fields

# C++
 ['name',       'ros::init\([^\)]*' + QSTRING + '\)',               ['name']],  
 ['spin',       'ros::spin\(\)',                                    []],
 ['publ',       'publish\(\s*',                                    []],  
 ['sub',        'subscribe' + GENERIC + '\(' + QSTRING,             ["type", "name"]], 
 ['sub',        'subscribe\(' + QSTRING + '\s*',                            ["name"]], 
 ['pub',        'advertise' + GENERIC + '\s*\(' + QSTRING,             ['type', 'name']],
 ['param',      'param()\(' + QSTRING + ', [^,]+, ([^\)]+)\)',      ['type', 'name', 'default']], 
 ['param',      'param' + GENERIC + '\(' + QSTRING + ', [^,]+' + FINAL_PARAM, ['type', 'name', 'default']],
 ['param',      'getParam\(' + QSTRING,                             ['name']], 
 ['param',      'param::get\(' + QSTRING,                           ['name']], 
 ['param_set',  'setParam\(' + QSTRING,                             ['name']], 
 ['param_set',  'param::set\(' + QSTRING,                           ['name']], 
 ['srv',        'advertiseService\(' + QSTRING,                     ['name']], #C++ service *SHOULD SET TYPE
 ['srv_called', 'advertiseService' + GENERIC + '\(' + QSTRING,      ['type', 'name']],
 ['nodehandle',       'ros::NodeHandle \s*',                        []],
 ['subscriber_def',       'ros::Subscriber \s*',                        []],
 ['publisher_def',       'ros::Publisher \s*',                        []],


# Python
 ['name',       'rospy.init_node\(' + PSTRING,                      ['name']], 
 ['sub',        'rospy.Subscriber\('+ PSTRING + NEXT_PARAM + ',',   ['name', 'type']], 
 ['pub',        'rospy.Publisher\(' + PSTRING + FINAL_PARAM,        ['name', 'type']], 
 ['param',      'rospy.get_param\(' + PSTRING + '\)',               ['name']],  
 ['param',      'rospy.get_param\(' + PSTRING + FINAL_PARAM,        ['name', 'default']], 
 ['param_set',  'rospy.set_param\(' + PSTRING,                      ['name']], 
 ['srv',        'rospy.Service\(' + PSTRING + NEXT_PARAM + ',',     ['name', 'type']],
 ['srv_called', 'rospy.ServiceProxy\(' + PSTRING + FINAL_PARAM,     ['name', 'type']],

# Python or C++
 ['req_tf',     'lookupTransform\(' + PSTRING + ', ' + PSTRING,     ['from', 'to']],
 ['prov_tf',    'sendTransform\(.*' + NEXT_PARAM + FINAL_PARAM,     ['from', 'to']], # DOES NOT WORK
]

class PackageData():
	name = ""
	author = ""
	url = ""
	description =""
	nodes = []

	"""object holding package information"""
	def __init__(self):
		pass

class NodeData():
	name = ""
	publishers = []
	subscribers = []
	serviceservers = []
	serviceclients = []
	parameters = []

	def __init__(self):
		pass


class Parser():
	"""A source code parser for ROS code based on ros_wiki node
	Will analyze a ROS package and extract all information
	"""

	parsed_lines = []

	def __init__(self, package_name):
		self.packdat = PackageData()
		r = rospkg.RosPack()
		m = r.get_manifest(package_name)
		self.packdat.author = m.author
		self.packdat.description = m.description
		self.packdat.url = m.url
		path = r.get_path(package_name)
		cppfiles = []
		for r,d,f in os.walk(path):
			for files in f:
				if files.endswith(".cpp"):
					cppfiles.append(os.path.join(r,files))
		self.parsed_lines = self.parse_line_by_line(cppfiles)
		#fill node information

	# Deletes all comments, empty lines and parenthesis lines from source code
	def strip_comments_and_parenteses(self, lines, debug=False):
		#REG EX for comments
		comment_pattern = r"(/\*([^*]|[\r\n]|(\*+([^*/]|[\r\n])))*\*+/)|(//.*)|(^\*)|(^\/\*)"
		comment_pattern2 = r"(\s*)(.*?)(//.*)"
		stripped_lines = []
		stripped_lines2 = []
		stripped_lines3 = []
		if(debug):
			print "Before stripping: ", str(len(lines))
		for line in lines:
			found = 0
			for match in re.findall(comment_pattern, line.strip()):
				found = 1
			if(found == 0 and len(line.strip()) != 0):
				stripped_lines.append(line)

		if(debug):
			print "After first stripping: ", str(len(stripped_lines))
		#REG EX for parenthesis
		parenthesis_pattern = r"^(\{|\})"
		for line in stripped_lines:
			found = 0
			for match in re.findall(parenthesis_pattern, line.strip()):
				found = 1
			if(found == 0):
				stripped_lines2.append(line)
		if(debug):
			print "After second stripping: ", str(len(stripped_lines2))
		include_pattern = r"^(\#include)"
		for line in stripped_lines2:
			found = 0
			for match in re.findall(include_pattern, line.strip()):
				found = 1
			if(found == 0):
				stripped_lines3.append(line)


		return stripped_lines3

	# Parses lines for ROS source code
	def parse_line_by_line(self, filenames):
		lines = []
		for filename in filenames:
			f = open(filename, 'r')
			flines = f.readlines()
			flines = self.strip_comments_and_parenteses(flines)
			f.close()
			print "File " + filename + " with " + str(len(flines)) + " stripped lines."
			lines = lines + flines
		mmap = {}
		line_number = 0
		parsed_lines = []

		for line in lines:
			found = 0
			for (cat, pattern, fields) in PATTERNS:
				for match in re.findall(pattern, line.strip()):
					#print "###", line_number, match, fields, cat
					found = cat
					mmap = {}
					if len(fields) > 1:
						for key, value in zip(fields, match):
							mmap[key] = value
							#print "key, value: ", key, value
							#print "###########" 
			parsed_lines.append([line_number, found, line.rstrip(), mmap])
			line_number+=1
		print "Hurray! Parsed " + str(len(lines)) + " lines."
		return parsed_lines

if __name__ == "__main__":
	if(len(sys.argv) == 2):
		p = Parser(sys.argv[1])
