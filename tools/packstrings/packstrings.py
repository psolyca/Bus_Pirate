#!/usr/bin/env python3

import argparse
import csv
import io
import sys

if sys.hexversion < 0x03000000:
    raise Exception('Cannot run on anything earlier than Python 3.0')

MAPPING_OUT = {
    '\\' : '\\\\',
    '\r' : '\\r',
    '\n' : '\\n',
    '\t' : '\\t',
    '"' : '\\"'
}

def unquote_string(string):
    new_string = io.StringIO()

    escape = False
    hex_escape = False
    hex_buffer = ''

    for character in string:
        if hex_escape:
            hex_buffer += character
            if len(hex_buffer) == 2:
                hex_code = int(hex_buffer, 16)
                new_string.write(chr(hex_code))
                hex_buffer = ''
                hex_escape = False
                escape = False
            continue

        if escape:
            if character == 'n':
                new_string.write('\n')
            elif character == 'r':
                new_string.write('\r')
            elif character == 't':
                new_string.write('\t')
            elif character == '"':
                new_string.write('"')
            elif character == '\\':
                new_string.write('\\')
            elif character == 'x':
                hex_code = 0
                hex_escape = True
                escape = False
                continue
            else:
                print(character)
            escape = False
            continue

        if character != '\\':
            new_string.write(character)
        else:
            escape = True

    if escape or hex_escape:
        raise Exception('Invalid string: "%s"' % string)

    return new_string.getvalue()


def get_messages(handle):
    read_lines = []

    for row in csv.reader(handle, delimiter='\t', quotechar='\\',
                          dialect='unix'):
        if len(row) == 0:
            continue
        stripped = row[0].strip()
        if stripped.startswith('#'):
            items = stripped.split()
            if items[0] == '#include':
                with open(' '.join(items[1:]), 'r') as include_handle:
                    include_lines = get_messages(include_handle)
                    if len(include_lines) > 0:
                        read_lines += include_lines
            continue
        if len(row) != 3:
            continue
        if row[0].strip().startswith('//'):
            continue
        if row[1] not in ('0', '1'):
            continue
        row[2] = row[2].strip()
        if not (row[2].startswith('"') and row[2].endswith('"')):
            continue
        row[2] = unquote_string(row[2][1:-1])

        read_lines.append(row)

    return read_lines


parser = argparse.ArgumentParser(
    description='Pack Bus Pirate strings into something that can be '
                'included by the firmware.')
parser.add_argument('source', metavar='TEXT',
                    type=argparse.FileType('r'), help='the string file')
parser.add_argument('outbase', metavar='OUTPUT', type=str,
                    help='the base filename for output files')
parser.add_argument('guard', metavar='GUARD', type=str,
                    help='an additional marker to put in the C header '
                         '#include guard block')

args = parser.parse_args()
lines = get_messages(args.source)

with open(f'{args.outbase}.s', 'w') as assembly_output:
    for row in sorted(lines):
        assembly_output.write('\t; %s\n' % row[0])
        assembly_output.write('\t.section .text.%s, code\n' % row[0])
        assembly_output.write('\t.global _%s_str\n' % row[0])
        assembly_output.write('_%s_str:\n' % row[0])
        assembly_output.write('\t.pasciz ')
        string_segments = []
        for character in row[2]:
            if character in MAPPING_OUT:
                if string_segments and type(string_segments[-1]) == str:
                    string_segments[-1] += MAPPING_OUT[character]
                else:
                    string_segments.append(MAPPING_OUT[character])
            elif (ord(character) < 0x20) or (ord(character) > 0x7E):
              string_segments.append(ord(character))
            elif not string_segments or type(string_segments[-1]) != str:
                string_segments.append(character)
            else:
                string_segments[-1] += character
        for segment_index in range(len(string_segments)):
          segment = string_segments[segment_index]
          if type(segment) == str:
            assembly_output.write('"%s"' % segment)
          else:
            assembly_output.write('<%d>' % segment)
          if segment_index < (len(string_segments) - 1):
            assembly_output.write(', ')
          else:
            assembly_output.write('\n\n')

offset = 0
BUFFER_WRITE_CALL = 'bp_message_write_buffer'
LINE_WRITE_CALL = 'bp_message_write_line'

with open(f'{args.outbase}.h', 'w') as header_output:
    header_output.write('#ifndef BP_MESSAGES_%s_H\n' % args.guard.upper())
    header_output.write('#define BP_MESSAGES_%s_H\n\n' % args.guard.upper())

    for row in sorted(lines):
        call = BUFFER_WRITE_CALL if row[1] == '0' else LINE_WRITE_CALL
        header_output.write('void %s_str(void);\n' % row[0])
        header_output.write('#define %s %s(__builtin_tbladdress(%s_str))\n' %
                            (row[0], call, row[0]))
        offset += len(row[2])

    header_output.write('\n#endif /* BP_MESSAGES_%s_H */\n' %
                        args.guard.upper())

# vim:sts=2:sw=2:ts=2:et:syn=python:fdm=marker:ff=unix:fenc=utf-8:number:cc=80
