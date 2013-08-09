#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import with_statement

import re
import sys
from glob import glob
from os import path
from subprocess import Popen, PIPE
from sys import argv

# Local module: generator for texture lookup builtins
from texture_builtins import generate_texture_functions

builtins_dir = path.join(path.dirname(path.abspath(__file__)), "..")

# Get the path to the standalone GLSL compiler
if len(argv) != 2:
    print "Usage:", argv[0], "<path to compiler>"
    sys.exit(1)

compiler = argv[1]

# Read the files in builtins/ir/*...add them to the supplied dictionary.
def read_ir_files(fs):
    for filename in glob(path.join(path.join(builtins_dir, 'ir'), '*.ir')):
        function_name = path.basename(filename).split('.')[0]
        with open(filename) as f:
            fs[function_name] = f.read()

def read_glsl_files(fs):
    for filename in glob(path.join(path.join(builtins_dir, 'glsl'), '*.glsl')):
        function_name = path.basename(filename).split('.')[0]
        (output, returncode) = run_compiler([filename])
        if (returncode):
            sys.stderr.write("Failed to compile builtin: " + filename + "\n")
            sys.stderr.write("Result:\n")
            sys.stderr.write(output)
        else:
            fs[function_name] = output;

# Return a dictionary containing all builtin definitions (even generated)
def get_builtin_definitions():
    fs = {}
    generate_texture_functions(fs)
    read_ir_files(fs)
    read_glsl_files(fs)
    return fs

def stringify(s):
    # Work around MSVC's 65535 byte limit by outputting an array of characters
    # rather than actual string literals.
    if len(s) >= 65535:
        #t = "/* Warning: length " + repr(len(s)) + " too large */\n"
        t = ""
        for c in re.sub('\s\s+', ' ', s):
            if c == '\n':
                t += '\n'
            else:
                t += "'" + c + "',"
        return '{' + t[:-1] + '}'

    t = s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n"\n   "')
    return '   "' + t + '"\n'

def write_function_definitions():
    fs = get_builtin_definitions()
    for k, v in sorted(fs.iteritems()):
        print 'static const char builtin_' + k + '[] ='
        print stringify(v), ';'

def run_compiler(args):
    command = [compiler, '--dump-hir'] + args
    p = Popen(command, 1, stdout=PIPE, shell=False)
    output = p.communicate()[0]

    if (p.returncode):
        sys.stderr.write("Failed to compile builtins with command:\n")
        for arg in command:
            sys.stderr.write(arg + " ")
        sys.stderr.write("\n")
        sys.stderr.write("Result:\n")
        sys.stderr.write(output)

    # Clean up output a bit by killing whitespace before a closing paren.
    kill_paren_whitespace = re.compile(r'[ \n]*\)', re.MULTILINE)
    output = kill_paren_whitespace.sub(')', output)

    # Also toss any duplicate newlines
    output = output.replace('\n\n', '\n')

    # Kill any global variable declarations.  We don't want them.
    kill_globals = re.compile(r'^\(declare.*\n', re.MULTILINE)
    output = kill_globals.sub('', output)

    return (output, p.returncode)

def write_profile(filename, profile):
    (proto_ir, returncode) = run_compiler([filename])

    if returncode != 0:
        print '#error builtins profile', profile, 'failed to compile'
        return

    print 'static const char prototypes_for_' + profile + '[] ='
    print stringify(proto_ir), ';'

    # Print a table of all the functions (not signatures) referenced.
    # This is done so we can avoid bothering with a hash table in the C++ code.

    function_names = set()
    for func in re.finditer(r'\(function (.+)\n', proto_ir):
        function_names.add(func.group(1))

    print 'static const char *functions_for_' + profile + ' [] = {'
    for func in sorted(function_names):
        print '   builtin_' + func + ','
    print '};'

def write_profiles():
    profiles = get_profile_list()
    for (filename, profile) in profiles:
        write_profile(filename, profile)

def get_profile_list():
    profile_files = []
    for extension in ['glsl', 'frag', 'vert']:
        path_glob = path.join(
            path.join(builtins_dir, 'profiles'), '*.' + extension)
        profile_files.extend(glob(path_glob))
    profiles = []
    for pfile in sorted(profile_files):
        profiles.append((pfile, path.basename(pfile).replace('.', '_')))
    return profiles

if __name__ == "__main__":
    print """/* DO NOT MODIFY - automatically generated by generate_builtins.py */
/*
 * Copyright © 2010 Intel Corporation
 *
 * Permission is hereby granted, free of charge, to any person obtaining a
 * copy of this software and associated documentation files (the "Software"),
 * to deal in the Software without restriction, including without limitation
 * the rights to use, copy, modify, merge, publish, distribute, sublicense,
 * and/or sell copies of the Software, and to permit persons to whom the
 * Software is furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice (including the next
 * paragraph) shall be included in all copies or substantial portions of the
 * Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL
 * THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
 * FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
 * DEALINGS IN THE SOFTWARE.
 */

#include <stdio.h>
#include "main/core.h" /* for struct gl_shader */
#include "glsl_parser_extras.h"
#include "ir_reader.h"
#include "program.h"
#include "ast.h"

extern "C" struct gl_shader *
_mesa_new_shader(struct gl_context *ctx, GLuint name, GLenum type);

gl_shader *
read_builtins(GLenum target, const char *protos, const char **functions, unsigned count)
{
   struct gl_context fakeCtx;
   fakeCtx.API = API_OPENGL_COMPAT;
   fakeCtx.Const.GLSLVersion = 140;
   fakeCtx.Extensions.ARB_ES2_compatibility = true;
   fakeCtx.Extensions.ARB_ES3_compatibility = true;
   fakeCtx.Const.ForceGLSLExtensionsWarn = false;
   gl_shader *sh = _mesa_new_shader(NULL, 0, target);
   struct _mesa_glsl_parse_state *st =
      new(sh) _mesa_glsl_parse_state(&fakeCtx, target, sh);

   st->language_version = 140;
   st->symbols->separate_function_namespace = false;
   st->ARB_texture_rectangle_enable = true;
   st->EXT_texture_array_enable = true;
   st->OES_EGL_image_external_enable = true;
   st->ARB_shader_bit_encoding_enable = true;
   st->ARB_texture_cube_map_array_enable = true;
   st->ARB_shading_language_packing_enable = true;
   _mesa_glsl_initialize_types(st);

   sh->ir = new(sh) exec_list;
   sh->symbols = st->symbols;

   /* Read the IR containing the prototypes */
   _mesa_glsl_read_ir(st, sh->ir, protos, true);

   /* Read ALL the function bodies, telling the IR reader not to scan for
    * prototypes (we've already created them).  The IR reader will skip any
    * signature that does not already exist as a prototype.
    */
   for (unsigned i = 0; i < count; i++) {
      _mesa_glsl_read_ir(st, sh->ir, functions[i], false);

      if (st->error) {
         printf("error reading builtin: %.35s ...\\n", functions[i]);
         printf("Info log:\\n%s\\n", st->info_log);
         ralloc_free(sh);
         return NULL;
      }
   }

   reparent_ir(sh->ir, sh);
   delete st;

   return sh;
}
"""

    write_function_definitions()
    write_profiles()

    profiles = get_profile_list()

    print 'static gl_shader *builtin_profiles[%d];' % len(profiles)

    print """
static void *builtin_mem_ctx = NULL;

void
_mesa_glsl_release_functions(void)
{
   ralloc_free(builtin_mem_ctx);
   builtin_mem_ctx = NULL;
   memset(builtin_profiles, 0, sizeof(builtin_profiles));
}

static void
_mesa_read_profile(struct _mesa_glsl_parse_state *state,
                   int profile_index,
		   const char *prototypes,
		   const char **functions,
                   int count)
{
   gl_shader *sh = builtin_profiles[profile_index];

   if (sh == NULL) {
      sh = read_builtins(GL_VERTEX_SHADER, prototypes, functions, count);
      ralloc_steal(builtin_mem_ctx, sh);
      builtin_profiles[profile_index] = sh;
   }

   state->builtins_to_link[state->num_builtins_to_link] = sh;
   state->num_builtins_to_link++;
}

void
_mesa_glsl_initialize_functions(struct _mesa_glsl_parse_state *state)
{
   /* If we've already initialized the built-ins, bail early. */
   if (state->num_builtins_to_link > 0)
      return;

   if (builtin_mem_ctx == NULL) {
      builtin_mem_ctx = ralloc_context(NULL); // "GLSL built-in functions"
      memset(&builtin_profiles, 0, sizeof(builtin_profiles));
   }
"""

    i = 0
    for (filename, profile) in profiles:
        if profile.endswith('_vert'):
            check = 'state->target == vertex_shader && '
        elif profile.endswith('_frag'):
            check = 'state->target == fragment_shader && '
        else:
            check = ''

        version = re.sub(r'_(glsl|vert|frag)$', '', profile)
        if version[0].isdigit():
            is_es = version.endswith('es')
            if is_es:
                version = version[:-2]
            check += 'state->language_version == ' + version
            check += ' && {0}state->es_shader'.format('' if is_es else '!')
        else: # an extension name
            check += 'state->' + version + '_enable'

        print '   if (' + check + ') {'
        print '      _mesa_read_profile(state, %d,' % i
        print '                         prototypes_for_' + profile + ','
        print '                         functions_for_' + profile + ','
        print '                         Elements(functions_for_' + profile + '));'
        print '   }'
        print
        i = i + 1
    print '}'

