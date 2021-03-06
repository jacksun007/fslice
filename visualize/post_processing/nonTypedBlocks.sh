# Non Typed Blocks - gives us a list of blocks whose sub-elements are not accessed

echo "Usage ./nonTypedBlocks.sh <taintFile>"

TAINT_FILE=${1:-/tmp/testfs.py}

rm -rf blockTaints operations blockNumbers #operations
rm -rf forwardTrace forwardTraceTemplate
mkdir forwardTrace
mkdir forwardTraceTemplate

cat $TAINT_FILE | sed '/^#/ d' | grep -v "^#" | grep "B(64," | cut -d"=" -f1 >> blockTaints

cat $TAINT_FILE | sed '/^#/ d' | grep -v "^#" | grep "B(64," | cut -d"," -f2 >> blockNumbers

paste -d" " blockTaints blockNumbers > TaintBlockFile

while read line; do
	taint=`echo $line | cut -d" " -f1`
	blockNum=`echo $line | cut -d" " -f2`
	taintBlockHash[$taint]=$blockNum
done < TaintBlockFile

cat $TAINT_FILE | sed '/^#/ d' | cut -d"=" -f2 >> operations

python nonTypedBlocks.py operations blockTaints TaintBlockFile

rm -rf blockTaints operations blockNumbers #operations
