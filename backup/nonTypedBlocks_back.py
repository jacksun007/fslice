# gives all blocks whose sub elements have not been accessed
# usage ./nonTypedBlocks.py operations blockTaints TaintBlockFile
# usage ./nonTypedBlocks.py operations blockTaints TaintBlockFile

import sys
import os
from returnBlockNoAndOffset import returnBlockNoAndOffset
from forwardTraceContainsBlock import forwardTraceContainsBlock
from forwardTraceReferencesSubelements import forwardTraceReferencesSubelements
from collections import defaultdict
from pprint import pprint

blockSize = 64
blockContentMap = defaultdict(list)
blockLabelMap = {}

def usage():
	print "usage ./nonTypedBlocks.py operations blockTaints TaintBlockFile"
	sys.exit()

# Right hand side of all taint assignment operations
def loadOperations(operationsFile):
	operations = list(open(operationsFile,'r'))
	operations = map(lambda s: s.strip(), operations)
	return operations

# taint number of blocks
def loadBlockTaints(blockTaintFile):
	blockTaints = list(open(sys.argv[2],'r'))
	blockTaints = map(lambda s: s.strip(), blockTaints)
	return blockTaints

def getBackTraceBlock(block, taintList):
	#print "In getBackTraceBlock ",block,taintList
	#table = [{}]
	srcBlockOffsetMap = {}
	for taint in taintList:
		(srcBlockNo,offsetList) = returnBlockNoAndOffset(taint, '/tmp/testfs.py')
		if srcBlockNo is not None:
			srcBlockOffsetMap[srcBlockNo]=offsetList
			#table.append(srcBlockOffsetMap)
	return srcBlockOffsetMap# (srcBlockNo,table)

def initDataStructures(taintBlockFile): # <tNo BlockNo>
	with open(sys.argv[3],'r') as f:
		for line in f:
			(taint, block) = line.split()
			taintBlockMap[taint] = block
			blockTaintDictionary[block].append(taint)	
	return (taintBlockMap, blockTaintDictionary)

def getTypeInfo(taintBlockMap,blockTaintDictionary):
	for taint in taintBlockMap:
		isNonTypedBlock=True
		block=taintBlockMap[taint]
		if forwardTraceContainsBlock(taint,'/tmp/testfs.py') is False: # not Typed
		#if forwardTraceReferencesSubelements(taint,'/tmp/testfs.py') is False: # not Typed
			if list(set(blockTaintDictionary[block]) & set(typedBlockTaintList)) == []:
				#print "Non Typed Block",block # Non Typed Block
				nonTypedBlocks.append(block)
			else:	
				#print "Typed Block", block, taint
				typedBlocks.append(block)
				typedBlockTaintList.append(taint)
				while block in nonTypedBlocks:
					nonTypedBlocks.remove(block)
		else:
			typedBlocks.append(block)
			typedBlockTaintList.append(taint)
			while block in nonTypedBlocks:
				nonTypedBlocks.remove(block)
	return (typedBlocks,nonTypedBlocks)	

def getBlocksWithSubStructuresAccessed(nonTypedBlocks,taintBlockMap,blockTaintDictionary):
	subStructReferedBlocks = []
	typedBlocks = []
	for taint in taintBlockMap:
		if taintBlockMap[taint] not in nonTypedBlocks:
			continue
		isNonTypedBlock=True
		block=taintBlockMap[taint]
		#if forwardTraceContainsBlock(taint,'/tmp/testfs.py') is False: # not Typed
		if forwardTraceReferencesSubelements(taint,'/tmp/testfs.py') is False: # not Typed
			if list(set(blockTaintDictionary[block]) & set(typedBlockTaintList)) == []:
				#print "Non Typed Block",block # Non Typed Block
				subStructReferedBlocks.append(block)
			else:	
				#print "Typed Block", block, taint
				typedBlocks.append(block)
				typedBlockTaintList.append(taint)
				while block in subStructReferedBlocks:
					subStructReferedBlocks.remove(block)
		else:
			typedBlocks.append(block)
			typedBlockTaintList.append(taint)
			while block in subStructReferedBlocks:
				subStructReferedBlocks.remove(block)
	return typedBlocks

def blockExists(key,MapTtoT):
	blockNum = (key.split('.')[0])
	for key in MapTtoT:
		if blockNum in key.lower():
			return True
	return False
		
# penultimate blocks are those blocks which only have non-typed blocks (leaf blocks) in the tree as destination pointers
# if any blocks contain both non-typed blocks and typed-blocks, they are not considered penultimate blocks.

def getPenultimateBlocks(MapTtoT, MapTtoNT):
	penultimateBlockMap = {}
	for key in MapTtoNT:
		if blockExists(key,MapTtoT) is False:
			penultimateBlockMap[key] = MapTtoNT[key]
	return penultimateBlockMap

# refresh block map list, after some blocks have been typed, delete them
def removeTypedBlocks(penultimateBlockMap,MapTtoT,MapTtoNT):
	MapTtoNT = { k : v for k, v in MapTtoNT.items() if k not in penultimateBlockMap}
	return (penultimateBlockMap,MapTtoT,MapTtoNT)	
	
# returns Map of type {DX : [B0,B1,B2]}
def createLabelMap():
	global blockLabelMap
	print "createLabelMap"
	labelBlockMap = defaultdict(list)
	for block,label in blockLabelMap.items():
		labelBlockMap[label].append(block)
	print "labelBlockMap---"
	#for label,blockList in labelBlockMap.items():
	#	print label,blockList
	return labelBlockMap			
	
def derivePattern(block):
	global blockContentMap
	pattern = {}
	index = 0

	if block in blockContentMap:
		contents = blockContentMap[block]
	else:
		return pattern
	while True:
		start_idx = index
		value = contents[index]
		while (index < (len(contents))) and (value in contents[index]):
			index+=1
		pattern[str(start_idx) + '-' + str(index - 1)] = value
		if index >= (len(contents) -1):
			break

	print "block ",block," pattern ",pattern
	return pattern

# this function will partition same labeled blocks or join different labeled blocks based
# on rules. It updates corresponding entries in blockLabelMap and blockContentMap

def clusterTypes():
	global blockLabelMap
	global blockContentMap
	labelBlockMap = createLabelMap()
	pattern = defaultdict(map)
	for label,blockList in labelBlockMap.items():
		for block in blockList:
			pattern[block] = derivePattern(block)
		
	
def labelBlocks():
	global blockLabelMap
	global blockContentMap
	for k,v in blockContentMap.items():
		labelList = []
		#if k not in blockLabelMap: # block not Typed yet
		for element in v:
			if 'D' in element:
				labelList.append(element)
		if labelList:	# found block pointers
				# TODO currently dumb algorithm, categorizes all blocks based on 
				# contents of the blocks. need to bring more intelligence - based
				# on start offset etc.
			label = max(labelList).split('D')[1]
			blockLabelMap[k] = 'D'+str(int(label)+1)
			#print "XXXX--labelBlocks = ",k,blockLabelMap[k]
		else:	# no block pointers found
			if k not in blockLabelMap:
				blockLabelMap[k] = 'D0'

# fill blockContentMap with types
# from Map, detect the source block and offsets. From destination, check for the maximum label
# among destination blocks, assign 1 higher label to source block.

def createTemplate(Map):
	global blockContentMap
	ptrType = ''
	srcPtrType = 'D1'
	for k,v in Map.items():
		blockNum = k.split('.')[0].split('b')[1]
		if blockNum not in blockContentMap:
			blockContentMap[blockNum] = ['U']*blockSize
			if not ptrType:
				ptrType = 'D0'
		else:
			if not [s for s in blockContentMap[blockNum] if 'D' in s]:
				if not ptrType:
					ptrType = 'D0'
			else:
				if not ptrType:
					ptrType = max([s for s in blockContentMap[blockNum] if 'D' in s])
					srcPtrType = 'D'+str(int(ptrType.split('D')[1])+1)

		offset = k.split('.')[1]
		offsetList = offset.split('-')
		#print "createTemplate => blockNum ",blockNum
		if blockNum not in blockLabelMap:
			blockLabelMap[blockNum] = srcPtrType
		for off in offsetList:
			for destBlock in v:
				if destBlock in blockLabelMap: # if multiple data labels are pointed to by src offset,
								# choose largest label and assign it to blockContentMap
					ptrType = blockLabelMap[destBlock]
			blockContentMap[blockNum][int(off)] = ptrType

#	for block in blockContentMap:
#		print block,blockContentMap[block]
	
# for all leaf blocks, initialize blockContentMap and blockLabelMap
# all values in MapTtoNT are nonTyped. so mark them non-typed
def markLeafBlocks(MapTtoNT):
	for k,destBlockList in MapTtoNT.items():
		#print "leaf Blocks ",destBlockList
		for destinationBlock in destBlockList:
			blockContentMap[destinationBlock] = ['U']*blockSize
			blockLabelMap[destinationBlock] = 'D0'
			
def getSourcePointerMap(destinationblockList,MapTtoT, MapTtoNT):
	sourcePointerMap = defaultdict(list)
	for block in destinationblockList:
		blockNum = block.split('b')[1]
		for k,v in MapTtoT.items():
			if blockNum in v:
				sourcePointerMap[k] = blockNum
		for k,v in MapTtoNT.items():
			if blockNum in v:
				sourcePointerMap[k] = blockNum
	return sourcePointerMap

def getSourceBlocks(sourcePointerMap):
	sourceBlockList = []
	for block in sourcePointerMap:
		blockNum = block.split('.')[0].split('b')[1]
		sourceBlockList.append(blockNum)
	return sourceBlockList

def scanMap(sourceBlockList,Map):
	nextLevelList = []
	ptrType = 'D0'
	print "scanMap"
	for block in sourceBlockList:
		print "block - ",block
		for srcBlk, destBlockList in Map.items():
			srcBlock = srcBlk.split('.')[0].split('b')[1]
			if srcBlock == block:
				print "srcBlock", srcBlock ," is block ",block
				for destBlk in destBlockList:
					if destBlk not in blockLabelMap:
						# check if it exists in blockContentMap
						if destBlk not in blockContentMap:
							nextLevelList.append(block)
						else:
							createTemplate({srcBlk : destBlk})	
					else:
						createTemplate({srcBlk : destBlockList})
						labelBlocks()
				#		if 'D' in blockLabelMap[destBlk]:
				#			#print 'XXXXXX blockLabelMap for destination Block',destBlk,blockLabelMap[destBlk]
				#			#ptrType = max('D0', blockLabelMap[destBlk])
				#			#ptrType = 'D'+str(int(ptrType.split('D')[1])+1)
				#			#if srcBlock not in blockLabelMap or (blockLabelMap[srcBlock] < ptrType):
				#			#	blockLabelMap[srcBlock] = ptrType
				#			##print "calling createTemplate for ptrType ",ptrType," srcBlk ",srcBlk	
				#			#createTemplate({srcBlk : destBlockList})
				#		else:
				#			print "for srcBlock",srcBlock, " dest block", destBlk, " has label ",blockLabelMap[destBlk]
	print "nextLevelList",nextLevelList
	return sorted(set(nextLevelList))	


# if all destination blocks of source block list are typed, type the source
# block list as well. Return list of blocks that were not typed. These will
# be typed in the next iteration.

def assignLevel(sourceBlockList,MapTtoT, MapTtoNT): 
	nextLevelList = []
	nextLevelList = scanMap(sourceBlockList,MapTtoT)
	nextLevelList.append(scanMap(sourceBlockList,MapTtoNT))
	if not nextLevelList:	
		return []
	return (nextLevelList)


def getNextLevelBlocks(blockList,MapTtoT, MapTtoNT):
	#print blockList
	global blockLabelMap
	sourcePointerMap = getSourcePointerMap(blockList,MapTtoT, MapTtoNT)
	sourceBlockList = getSourceBlocks(sourcePointerMap)
	sourceBlockList = sorted(set(sourceBlockList))
	print "source Block List ",sourceBlockList
	typedBlockList = assignLevel(sourceBlockList,MapTtoT,MapTtoNT) 	
	for block in blockLabelMap:
		print block, blockLabelMap[block]
	return []

def extractSrcBlocks(Map):
	srcBlockList = []
	for src in Map:
		blockNum = src.split('.')[0]
		if blockNum not in srcBlockList:
			srcBlockList.append(blockNum)
	#print "srcBlockList",srcBlockList
	return srcBlockList
	
def classifyBlocks(MapTtoT,MapTtoNT):
	markLeafBlocks(MapTtoNT)
	labelBlocks()
	# blocks that exist in MapTtoNT and not in MapTtoT
	penultimateBlockMap = getPenultimateBlocks(MapTtoT, MapTtoNT)
	#(penultimateBlockMap,MapTtoT, MapTtoNT) = removeTypedBlocks(penultimateBlockMap, MapTtoT, MapTtoNT)
	createTemplate(penultimateBlockMap)
	labelBlocks()
	nextLevelBlocks = extractSrcBlocks(penultimateBlockMap)
	done = False
	while nextLevelBlocks or done is False:
		nextLevelBlocks = getNextLevelBlocks(nextLevelBlocks,MapTtoT, MapTtoNT)
		done = True
	clusterTypes()
	labelBlocks()
	return (penultimateBlockMap, MapTtoT, MapTtoNT)

if __name__ == "__main__":
	""" Main Start """

#	if len(sys.argv) != 4:
#		usage()
#	
	operations = loadOperations(sys.argv[1])
	blockTaints = loadBlockTaints(sys.argv[2])
#	
	taintBlockMap = {} # hash <taint - blockNum>
	MAP = {}
	MapTtoNT = defaultdict(list) 
	MapTtoT = defaultdict(list) 
	blockTaintDictionary = defaultdict(list) # <BNum - t1,t2,t3>
#	
	(taintBlockMap,blockTaintDictionary) = initDataStructures(sys.argv[3])

	# list of blocks that have Types i.e. their substructure elements have been accessed on RHS
	typedBlockTaintList = [] 
	nonTypedBlocks = []
	typedBlocks = []

#	# derive Non-Typed Blocks	
#	(typedBlocks, nonTypedBlocks) = getTypeInfo(taintBlockMap, blockTaintDictionary)
#	print "NON-TYPED OR UNINITIALIZED BLOCKS"
#	nonTypedBlocks = list(sorted(set(nonTypedBlocks)))
#	print nonTypedBlocks
#	
#	print "TYPED BLOCKS"
#	typedBlocks = list(sorted(set(typedBlocks)))
#	print typedBlocks
#
#	subStructureAccessedBlocks = getBlocksWithSubStructuresAccessed(nonTypedBlocks,taintBlockMap, blockTaintDictionary)
#	subStructureAccessedBlocks = list(sorted(set(subStructureAccessedBlocks)))
#	subStructureAccessedBlocks = [x for x in subStructureAccessedBlocks if x not in typedBlocks] 
#	print "SUB-STRUCTURE ACCESSED BLOCKS"
#	print subStructureAccessedBlocks
#
#	unknownBlocks = [x for x in nonTypedBlocks if x not in subStructureAccessedBlocks]
#	print "NON-TYPED BLOCKS"
#	print unknownBlocks 
#
#
#	
#	# get source block and offset for each destination block  
#	# generate backTraces

	nonTypedBlocks = ['1', '10', '11', '12', '13', '14', '15', '16', '17', '18', '19', '197', '198', '199', '2', '20', '200', '202', '203', '204', '205', '206', '207', '208', '209', '21', '210', '212', '213', '214', '215', '216', '217', '218', '219', '22', '220', '221', '222', '223', '224', '225', '226', '227', '228', '23', '230', '231', '232', '233', '234', '24', '25', '26', '27', '28', '29', '3', '30', '31', '32', '33', '34', '35', '36', '37', '38', '39', '4', '40', '41', '42', '43', '44', '45', '46', '47', '48', '49', '5', '50', '51', '52', '53', '54', '55', '56', '57', '58', '59', '6', '60', '61', '62', '63', '7', '8', '9'] 
	typedBlocks = ['0', '192', '193', '194', '195', '196', '201', '211', '229', '64', '65', '66', '67'] 

#	for destinationBlock in nonTypedBlocks:
#		#print "============"
#		#print block, blockTaintDictionary[block]
#		srcBlockOffsetMap = getBackTraceBlock(destinationBlock, blockTaintDictionary[destinationBlock])
#		#print destinationBlock,srcBlockOffsetMap 
#		for blk in srcBlockOffsetMap:
#			key = 'b'+str(blk)+'.'+str('-'.join(srcBlockOffsetMap[blk]))
#			MapTtoNT[key].append(destinationBlock)
#			#print key,'==>',SRC[key]
#	#	for key in sourceBlockAndOffset:
#	#		print key,srcBlock[key]
#
#	print "NON-TYPED BLOCK SRC PTRS"
#	for index in MapTtoNT:
#		MapTtoNT[index] = list(sorted(set(MapTtoNT[index])))
#	#	print index,MapTtoNT[index]
#	print MapTtoNT

	MapTtoNT = defaultdict(list, (('b66.16-17-18-19', ['198']),('b229.8-9-10-11', ['232']),('b211.0-1-2-3', ['212']),('b229.16-17-18-19', ['234']),('b66.56-57-58-59', ['210']),('b211.44-45-46-47', ['223']),('b0.16-17-18-19', ['197','198','199', '200', '202', '203', '204', '205', '206', '207', '208', '209', '210', '212', '213', '214', '215', '216', '217', '218', '219', '220', '221', '222', '223', '224', '225', '226', '227', '228', '230', '231', '232', '233', '234']),('b201.8-9-10-11', ['204']),('b201.0-1-2-3', ['202']),('b229.4-5-6-7', ['231']),('b211.12-13-14-15', ['215']),('b66.48-49-50-51', ['208']),('b66.12-13-14-15', ['197']),('b211.28-29-30-31', ['219']),('b0.4-5-6-7', ['2', '3']),('b211.8-9-10-11', ['214']),('b201.12-13-14-15', ['205']),('b229.12-13-14-15', ['233']),('b229.0-1-2-3', ['230']),('b66.52-53-54-55', ['209']),('b201.16-17-18-19', ['206']),('b67.20-21-22-23', ['227']),('b211.24-25-26-27', ['218']),('b211.32-33-34-35', ['220']),('b66.44-45-46-47', ['207']),('b0.0-1-2-3', ['1']),('b211.16-17-18-19', ['216']),('b66.24-25-26-27', ['200']),('b67.24-25-26-27', ['228']),('b211.40-41-42-43', ['222']),('b66.20-21-22-23', ['199']),('b211.4-5-6-7', ['213']),('b67.16-17-18-19', ['226']),('b64.12-13-14-15', ['4']),('b0.8-9-10-11', ['10','11', '12', '13', '14', '15', '16', '17', '18', '19', '20', '21', '22', '23', '24', '25', '26', '27', '28', '29', '30', '31', '32', '33', '34', '35', '36', '37', '38', '39', '4', '40', '41', '42', '43', '44', '45', '46', '47', '48', '49', '5', '50', '51', '52', '53', '54', '55', '56', '57', '58', '59', '6', '60', '61', '62', '63', '7', '8', '9']),('b211.48-49-50-51', ['224']),('b211.36-37-38-39', ['221']),('b201.4-5-6-7', ['203']),('b67.12-13-14-15', ['225']),('b211.20-21-22-23', ['217'])))

#	for block in typedBlocks:
#		#print "============"
#		srcBlockOffsetMap = getBackTraceBlock(block, blockTaintDictionary[block])
#		#print block,srcBlockOffsetMap
#		for blk in srcBlockOffsetMap:
#			key = 'b'+str(blk)+'.'+str('-'.join(srcBlockOffsetMap[blk]))
#			MapTtoT[key].append(block)
#			#print key,'==>',SRC[key]
#
#	print "TYPED BLOCK SRC PTRS"
#	for index in MapTtoT:
#		MapTtoT[index] = list(sorted(set(MapTtoT[index])))
#		print index,MapTtoT[index]
#
#	print MapTtoT 
#
	MapTtoT = defaultdict(list, (('b193.14-15-16-17', ['64']),('b196.14-15-16-17', ['66']),('b192.51-52-53-54', ['65']),('b0.12-13-14-15', ['64', '65', '66', '67']),('b64.12-13-14-15', ['192']),('b194.14-15-16-17', ['64']),('b66.60-61-62-63', ['211']),('b67.28-29-30-31', ['229']),('b195.14-15-16-17', ['64']),('b196.28-29-30-31', ['67']),('b64.16-17-18-19', ['196']),('b65.44-45-46-47', ['195']),('b0.16-17-18-19', ['193', '194', '195', '196', '201', '211', '229']),('b64.44-45-46-47', ['193']),('b66.28-29-30-31', ['201']),('b192.25-26-27-28', ['64']),('b65.12-13-14-15', ['194'])))

	(penultimateBlockMap,MapTtoT,MapTtoNT) = classifyBlocks(MapTtoT, MapTtoNT)
#	for block in sorted(penultimateBlockMap):
#		print block,penultimateBlockMap[block]

#	print "blockLabelMap"
#	for block in blockLabelMap:
#		print block,blockLabelMap[block]
#	print "MapTtoNT"
#	for elem in MapTtoNT:
#		print elem, MapTtoNT[elem]


