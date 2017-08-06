#!/usr/bin/python
# Copyright (C) Jean-Baptiste Cayrou
# This program is published under a MIT license
# 
# Tool that extracts co processor registers from XML ARM documentation:
# https://developer.arm.com/-/media/developer/products/architecture/armv8-a-architecture/ARMv83A-SysReg-00bet4.tar.gz?la=en
#
# Usage : python ./arm-doc-parser.py ./arm-doc/SysReg_v83A_xml-00bet4/

import sys
import os
import xml.etree.ElementTree as ET
import copy

DEBUG=0

def debug(str):
	if DEBUG:
		print str

# TODO : Should use classes like this ...
class cpreg_info:

	def __init__(self):
		self.reg_name = ""
		self.execution_state = 0
		self.inst_read_code = 0

		self.coproc = 0
		self.CRn = 0
		self.CRm = 0
		self.opc0 = 0
		self.opc1 = 0
		self.opc2 = 0


def parse_file(filename):

	print "Parsing file : %s ..." %filename
	obj_list = []
	obj = {}


	tree = ET.parse(filename)
	root = tree.getroot()

	root[0][0].attrib["execution_state"]


	execution_state = root.find("registers/register").attrib["execution_state"]
	reg_name = root.find("registers/register/reg_short_name").text
	instructions = root.find(".//*access_instructions")
 

	if instructions is None:
		return []

	access_instruction = root.find(".//*access_instruction").attrib["id"] # MRC, MRC2, MRRC, MRRC2 ,MRS, VMRS, MRS_br (banked)

 	if access_instruction in ["MRS_br", "VMRS"]:
 		return []

	varname = None

	for ins in instructions:
		if ins.tag == "defvar":
			tmp_varfields = {}
			obj = {}
			for vardef in ins:

				obj["execution_state"] = execution_state
				obj["access_instruction"] = access_instruction
				obj["CRn"] = 0 # CRn does not exist for MRRC
				obj["opc2"] = 0 # opc2 does not exist for MRRC

				if ("asmname" in vardef.attrib and vardef.attrib["asmname"] == "systemreg" ):
					obj["reg_name"] = vardef.attrib["asmvalue"] 			
				else:
					obj["reg_name"] = reg_name
				
				for enc in vardef:
					key = enc.attrib["n"]

					if "varname" in enc.attrib:
						tmp_varfields[key] = {}

						varname = enc.attrib["varname"]
						tmp_varfields[key]["varname"] = enc.attrib["varname"]
						tmp_varfields[key]["tmp_val"] = 0
						if key in ["CRn", "CRm"]:
							msb = 3
						elif key == "op0":
							msb = 1
						else:
							msb = 2
						tmp_varfields[key]["msb"] = msb
						tmp_varfields[key]["lsb"] = 0

					elif "width" in enc.attrib:
						encbit_val = 0
						for encbit in enc:
							if "v" in encbit.attrib:
								msb = int(encbit.attrib["msb"])
								lsb = int(encbit.attrib["lsb"])
								val = int(encbit.attrib["v"],2)

								encbit_val = encbit_val | (val &(msb-lsb + 1))<<lsb
							else:
								for encvar in encbit:
									tmp_varfields[key] = {}

									msb = int(encvar.attrib["msb"])
									lsb = int(encvar.attrib["lsb"])

									tmp_varfields[key]["varname"] = encvar.attrib["name"]
									tmp_varfields[key]["tmp_val"] = encbit_val
									tmp_varfields[key]["msb"] = msb
									tmp_varfields[key]["lsb"] = lsb

						
					else:
						val = int(enc.attrib["v"], 2)
					obj[key] = val

			# Need to generate all registers and replace REG_NAME<n> by 'n' values
			if len(tmp_varfields.keys())==0:
				obj_list.append(obj)
			else:
				tmp_gen_objs = [obj]

				for key, v in tmp_varfields.items():
					varname = v["varname"]
					debug("Generating %s field ..." % key)
					for variable in root.find(".//*reg_variables"):
						if variable.attrib["variable"] == varname:

							vals = []
							new_tmp_gen_objs = []

							if "max" in variable.attrib:
								nb_min = 0
								nb_max = int(variable.attrib["max"])
								vals = range(nb_min, nb_max)
							else:
																
								for reg_variable_val in variable:
									vals.append(int(reg_variable_val.text))

							debug("\t Gen list is : %r" %vals)
							for gen in vals:

								size_msk = v["msb"]-v["lsb"] + 1
								msk = int("1"*size_msk,2)
								gen_val = v["tmp_val"] | ( (gen&msk)<< v["lsb"] )
								
								debug("\t Generating %s=%d and val : %d" % (key, gen, gen_val))
								for tmp_obj in tmp_gen_objs:
									tmp_new_obj = copy.deepcopy(tmp_obj)
									if "varname_gen" not in tmp_new_obj:
										tmp_new_obj["varname_gen"]= {}
									gen_id = gen
									
									tmp_new_obj["varname_gen"][varname] = gen_id
 									tmp_new_obj[key] = gen_val
									new_tmp_gen_objs.append(tmp_new_obj)
								
							tmp_gen_objs = list(new_tmp_gen_objs) # Copy the list

							break
				# Update register name by remplacing <X> variables
				debug("Registers generated : %d " % len(tmp_gen_objs))
				for tmp_obj in tmp_gen_objs:

					for gen_name, gen_val  in tmp_obj["varname_gen"].items():
						tmp_obj["reg_name"] = tmp_obj["reg_name"].replace("<%s>"%gen_name, "%s"%gen_val)
				obj_list = tmp_gen_objs
	debug("****************************")
	debug(obj_list)
	debug("****************************")

	return obj_list


def gen_entries(objs):


	s = ""
	for obj in objs:

		reg_name = obj["reg_name"]
		
		if obj["execution_state"] == "AArch64":
			tmp = "{ ARM64_REG_%-16s, %4d, %4d, %4d, %4d, %4d, %4d },\n" % (reg_name, 0, obj["CRn"], obj["CRm"], obj["op0"], obj["op1"], obj["op2"])
		else:
			tmp = "{ ARM_REG_%-16s, %4d, %4d, %4d, %4d, %4d, %4d },\n" % (reg_name, obj["coproc"], obj["CRn"], obj["CRm"], 0, obj["opc1"], obj["opc2"])

		s += tmp

	return s

def aarch32_registers_files(xml_doc_path):

	filename = "AArch32-regindex.xml"

	if not os.path.exists(arm_xml_path +"/" +filename):
		print "Path Incorect"
		return

	tree = ET.parse("%s/%s" % (xml_doc_path, filename))
	root = tree.getroot()	
	regs = root.findall(".//*register_link")

	files = []
	for r in regs:
		f = r.attrib["registerfile"]
		files.append(f)


	registers = []

	for f in files:
		registers += parse_file(arm_xml_path + "/"+ f)

	print gen_entries(registers)


def aarch64_registers_files(xml_doc_path):

	filename = "AArch64-regindex.xml"

	if not os.path.exists(arm_xml_path +"/" +filename):
		print "Path Incorect"
		return

	tree = ET.parse(arm_xml_path +"/" +filename)
	root = tree.getroot()	
	regs = root.findall(".//*register_link")

	files = []
	for r in regs:
		f = r.attrib["registerfile"]
		files.append(f)


	registers = []

	for f in files:
		registers += parse_file(arm_xml_path + "/"+ f)

	print gen_entries(registers)


if __name__ == "__main__":

	if len(sys.argv) !=2:
		print "Usage : "
		print "%s <path_to_arm_xml_folder>"  % sys.argv[0]
		print "Where path point to 'SysReg_v83A_xml-00bet4/'"
		exit(1)

	arm_xml_path = sys.argv[1]
	if not os.path.exists(arm_xml_path):
		print "Path Incorect"
		exit(2)

aarch32_registers_files(arm_xml_path)
aarch64_registers_files(arm_xml_path)