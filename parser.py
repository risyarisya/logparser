import re
import json
import codecs
import csv
import argparse

p = argparse.ArgumentParser()
p.add_argument('-m', '--mode', type=str, default="check")
p.add_argument('-l', '--filename', type=str)
p.add_argument('-f', '--filter', type=str)
p.add_argument('-e', '--expect', type=str)
args = p.parse_args()

def make_regex(format_template):
    """
    Turn a format_template from %s into something like %[<>]?s
    """
    # FIXME support the return code format
    percent, rest = format_template[0], format_template[1:]
    return percent+"[<>]?"+rest


def extract_inner_value(input, sf):
    regex = re.compile("^%\{([^\}]+?)\}"+sf+"$")
    def matcher(matched_string):
        match = regex.match(matched_string)
        inner_value = match.groups()[0]
        inner_value = inner_value.strip().lower().replace("-", "_")
        return input+inner_value
    return matcher

FORMAT_STRINGS = [
    [make_regex('%\{[^\}]+?\}y'), '.*?', extract_inner_value('y_', 'y') , lambda matched_strings: matched_strings],
    [make_regex('%\{[^\}]+?\}n'), '.*?', extract_inner_value('n_', 'n') , lambda matched_strings: matched_strings],
]

class Parser:
    def __init__(self, format_string):
        self.names = []
        self.format_string = format_string
        self.pattern = "("+"|".join(x[0] for x in FORMAT_STRINGS)+")"
        self.parts = re.split(self.pattern, format_string)

        self.functions_to_parse = {}

        self.log_line_regex = ""
        while True:
            if len(self.parts) == 0:
                break
            if len(self.parts) == 1:
                raw, regex = self.parts.pop(0), None
            elif len(self.parts) >= 2:
                raw, regex = self.parts.pop(0), self.parts.pop(0)
            if len(raw) > 0:
                self.log_line_regex += re.escape(raw)
            if regex is not None:
                for format_spec in FORMAT_STRINGS:
                    pattern_regex, log_part_regex, name_func, values_func = format_spec
                    match = re.match("^"+pattern_regex+"$", regex)
                    if match:
                        name = name_func(match.group())
                        self.names.append(name)
                        self.functions_to_parse[name] = values_func
                        self.log_line_regex += "(?P<"+name+">"+log_part_regex+")"
                        break
        self._log_line_regex_raw = self.log_line_regex
        self.log_line_regex = re.compile(self.log_line_regex)
        self.names = tuple(self.names)

    def parse(self, log_line):
        match = self.log_line_regex.match(log_line)
        if match is None:
            raise LineDoesntMatchException(log_line=log_line, regex=self.log_line_regex.pattern)
        else:
            results = {}
            for name in self.functions_to_parse:
                values = {name: match.groupdict()[name]}
                values = self.functions_to_parse[name](values)
                results.update(values)
            return results


def make_parser(format_string):
    return Parser(format_string)

def extractFeature(parser, log):
    result = []
    for j in range(len(log)):
        for i in range(len(parser)):
            try: # find!
                tmp = parser[i].parse(log[j])
                result.append([i, j, {k:tmp[k] for k in tmp if k.split('_')[0]=='y'}])
                break
            except: # not find!
                pass
    return result

def loadFilter(filename):
    result  = []
    with open(filename, 'r') as f:
        reader = csv.reader(f)
        for row in reader:
            result.append(make_parser(row[1]+' '))
    return result

def loadLog(filename):
    with open(filename) as f:
        log = f.readlines()
        log = [l.strip()+" " for l in log]
    return log

def loadExpect(filename):
    def ascii_encode_dict(data):
        ascii_encode = lambda x: x.encode('ascii') if isinstance(x, unicode) else x
        return dict(map(ascii_encode, pair) for pair in data.items())
    # load expect
    with codecs.open(filename, 'r', 'utf-8') as f:
        expect = json.load(f, object_hook=ascii_encode_dict)
    return expect

def compare(expect, feature):
    # result
    if (expect==feature):
        print ("====== RESULT: [OK] ======")
    else:
        print ("====== RESULT: [NG] ======")
        for (e, f) in zip(expect, feature):
            ek, eli, ev = e
            fk, fli, fv = f
            print("[OK]" if (e==f) else "[NG]")
            evstr = ", ".join(k.split('_')[1]+"="+v for k, v in ev.items())
            print("[id:"+str(ek)+"] filter:  "+parser[ek].format_string)
            fvstr = ", ".join(k.split('_')[1]+"="+v for k, v in fv.items())
            if (ek==fk): # filter is same. contents is ng.
                print("  [expect] <"+evstr+">")
                print("  [log] <"+fvstr+">")
                print("  (L:"+str(fli+1)+") "+log[fli])
            else:
                # faild to find log.
                print(" [expect] <"+evstr+">") 
                print(" [log] NOT MATCH")

                
if (args.mode=="gen"):
    # generate expect
    log = loadLog(args.filename)
    parser = loadFilter(args.filter)
    expect = extractFeature(parser, log)
    # dump json file.
    with codecs.open(args.expect, 'w', 'utf-8') as f:
        dump = json.dumps(expect, ensure_ascii=False)
        f.write(dump)
    print(args.expect+" create.")
elif (args.mode=="check"):
    # check log.
    log = loadLog(args.filename)
    parser = loadFilter(args.filter)
    expect = loadExpect(args.expect)
    feature = extractFeature(parser, log)
    compare(expect, feature)


