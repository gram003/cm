import os
import re
from parse import *
from c import subroutine_c_name

MODULE_DOCSTRING = """OpenCMISS (Open Continuum Mechanics, Imaging, Signal processing and System identification)

A mathematical modelling environment that enables the application of finite
element analysis techniques to a variety of complex bioengineering problems.

This Python module wraps the underlying OpenCMISS Fortran library.

http://www.opencmiss.org
"""

INITIALISE = """WorldCoordinateSystem = CoordinateSystem()
WorldRegion = Region()
Initialise(WorldCoordinateSystem, WorldRegion)
ErrorHandlingModeSet(ErrorHandlingModes.ReturnErrorCode) #Don't output errors, we'll include trace in exception
"""

PREFIX='CMISS'

def generate(cm_path,args):
    """
    Generate the Python module that wraps the lower level C module created by SWIG
    """

    module = open(os.sep.join((cm_path,'bindings','python','opencmiss','CMISS.py')),'w')

    library = LibrarySource(cm_path)

    module.write('"""%s"""\n\n' % MODULE_DOCSTRING)
    module.write("import _opencmiss_swig\n")
    module.write("from _utils import CMISSError, CMISSType, Enum, wrap_cmiss_routine as _wrap_routine\n\n")

    types = sorted(library.lib_source.types.values(), key=attrgetter('name'))
    for type in types:
        module.write(type_to_py(type))

    for routine in library.unbound_routines:
        module.write(routine_to_py(routine))

    (enums, ungrouped_constants) = library.group_constants()
    for e in enums:
        if e.name.startswith(PREFIX):
            name = e.name[len(PREFIX):]
        else:
            name = e.name
        module.write("class %s(Enum):\n" % name)
        module.write('    """%s\n    """\n\n' % e.comment)
        constant_names = remove_prefix_and_suffix([c.name for c in e.constants])
        for (constant,constant_name) in zip(e.constants, constant_names):
            module.write("    %s = %d #%s\n" % (constant_name, constant.value, \
                    remove_doxygen_commands(constant.doxygen_comment)))
        module.write('\n')
    for c in ungrouped_constants:
        module.write("%s = %d #%s\n" % (c.name[5:], c.value, remove_doxygen_commands(c.doxygen_comment)))
    module.write('\n')

    module.write(INITIALISE)

    module.close()


def type_to_py(type):
    """Convert CMISS type to Python class"""

    cmiss_type = type.name[len(PREFIX):-len('Type')]
    docstring = remove_doxygen_commands('\n    '.join(type.comment_lines))

    py_class = "class %s(CMISSType):\n" % cmiss_type
    py_class += '    """%s\n    """\n' % docstring
    py_class += '\n\n'

    py_class += "    def __init__(self):\n"
    py_class += '        """Initialise a null %s"""\n\n' % type.name
    py_class += "        self.cmiss_type = _wrap_routine(_opencmiss_swig.%sInitialise, None)\n\n" % type.name

    for method in type.methods:
        if not method.name.endswith('TypeInitialise'):
            py_class += py_method(type, method)
    py_class += '\n'

    return py_class


def py_method(type, routine):
    """Write subroutine as method of Python class"""

    c_name = subroutine_c_name(routine)[0]
    name = c_name[len(type.name)-len('Type'):]
    if name == 'TypeFinalise':
        name = 'Finalise'
    create_start_name = type.name[:-len('Type')]+'CreateStart'

    if c_name.startswith(create_start_name):
        parameters = routine.parameters[:-1]
    else:
        parameters = routine.parameters[1:]

    py_args = [p.name for p in parameters if p.intent != 'OUT']
    method_args = ', '.join(['self']+py_args)
    if c_name.startswith(create_start_name):
        py_swig_args = ', '.join(py_args + ['self'])
    else:
        py_swig_args = ', '.join(['self'] + py_args)

    docstring = remove_doxygen_commands('\n        '.join(routine.comment_lines))
    docstring += '\n\n'
    docstring += ' '*8 + '\n        '.join(parameters_docstring(parameters).splitlines())
    docstring = docstring.strip()

    method = "    def %s(%s):\n" % (name, method_args)
    method += '        """%s\n        """\n\n' % docstring
    method += '        return _wrap_routine(_opencmiss_swig.%s, [%s])\n' % (c_name, py_swig_args)
    method += '\n'

    return method


def routine_to_py(routine):
    c_name = subroutine_c_name(routine)[0]
    name = c_name[len(PREFIX):]

    docstring = remove_doxygen_commands('\n    '.join(routine.comment_lines))
    docstring += '\n\n'
    docstring += ' '*4 +'\n    '.join(parameters_docstring(routine.parameters).splitlines())
    docstring = docstring.strip()

    args = ', '.join([p.name for p in routine.parameters if p.intent != 'OUT'])

    py_routine = "def %s(%s):\n" % (name, args)
    py_routine += '    """%s\n    """\n\n' % docstring
    py_routine += '    return _wrap_routine(_opencmiss_swig.%s, [%s])\n' % (c_name, args)
    py_routine += '\n\n'

    return py_routine


def parameters_docstring(parameters):
    """Create docstring section for parameters and return values"""

    return_values = []
    docstring = ""
    for param in parameters:
        if param.intent == 'OUT':
            return_values.append(param)
        else:
            docstring += ':param %s: %s\n' % (param.name, replace_doxygen_commands(param))
            docstring += ':type %s: %s\n' % (param.name, param_type_comment(param))
    return_comments = [return_comment(r) for r in return_values]
    if len(return_values) == 0:
        docstring += ':rtype: None\n'
    elif len(return_values) == 1:
        docstring += ':returns: %s\n' % (return_comments[0])
        docstring += ':rtype: %s\n' % (param_type_comment(return_values[0]))
    else:
        docstring += ':returns: (%s)\n' % (', '.join([c.rstrip('.') for c in return_comments]))
        docstring += ':rtype: tuple\n'

    return docstring


def return_comment(return_param):
    """Fix comment describing return value"""

    comment = replace_doxygen_commands(return_param)

    on_return = 'on return, '
    if comment.lower().startswith(on_return):
        comment = comment[len(on_return)].upper()+comment[len(on_return)+1:]
    if not comment.strip():
        return 'No description'
    return comment.strip()


PARAMETER_TYPES = {
    Parameter.INTEGER: 'int',
    Parameter.FLOAT: 'float',
    Parameter.DOUBLE: 'float',
    Parameter.CHARACTER: 'string',
    Parameter.LOGICAL: 'bool',
    Parameter.CUSTOM_TYPE: None
}


def param_type_comment(param):
    """Python type corresponding to Fortran type for use in docstrings"""

    if param.var_type == Parameter.CUSTOM_TYPE:
        type = param.type_name[len(PREFIX):-len('Type')]
    else:
        type = PARAMETER_TYPES[param.var_type]
    if param.array_dims == 1:
        if param.var_type == Parameter.CUSTOM_TYPE:
            type = "Array of %s objects" % type
        else:
            type = "Array of %ss" % type
    elif param.array_dims >= 1:
        if param.var_type == Parameter.CUSTOM_TYPE:
            type = "%dd list of %s objects" % (param.array_dims, type)
        else:
            type = "%dd list of %ss" % (param.array_dims, type)
    return type


def remove_doxygen_commands(comment):
    see_re = r'\.?\s*\\see\s*[^\s]*'
    match = re.search(see_re,comment)
    if match:
        comment = comment[0:match.start(0)]+comment[match.end(0):]
    return comment.strip()

def replace_doxygen_commands(param):
    """Replace doxygen see command with a reference to the appropriate Python enum class"""

    comment = param.doxygen

    if param.var_type == Parameter.INTEGER:
        see_re = r'\.?\s*\\see\s*OPENCMISS_([^\s,\.]*)'
        match = re.search(see_re,comment)
        if match:
            enum = match.group(1)
            if enum is not None:
                if enum.startswith(PREFIX):
                    enum = enum[len(PREFIX):]
                comment = comment[0:match.start(0)]
                if param.intent == 'IN':
                    comment += '. Must be a value from the '+enum+' enum.'
                else:
                    comment += '. Will be a value from the '+enum+' enum.'

    return comment

def remove_prefix_and_suffix(names):
    """Remove any common prefix and suffix from a list
    of enum names. These are redundant due to the enum
    class name"""

    if len(names) == 0:
        return names

    prefix_length = 0
    suffix_length = 0
    if len(names) == 1:
        #Special cases we have to specify
        if names[0] == 'CMISSControlLoopNode':
            prefix_length = len('CMISSControlLoop')
        elif names[0] == 'CMISSEquationsSetHelmholtzEquationTwoDim1':
            prefix_length = len('CMISSEquationsSetHelmholtzEquation')
        elif names[0] == 'CMISSEquationsSetPoiseuilleTwoDim1':
            prefix_length = len('CMISSEquationsSetPoiseuille')
        elif names[0] == 'CMISSEquationsSetFiniteElasticityCylinder':
            prefix_length = len('CMISSEquationsSetFiniteElasticity')
        else:
            sys.stderr.write("Warning: Found an unknown enum " \
                    "group with only one name: %s.\n" % names[0])
    else:
        min_length = min([len(n) for n in names])

        for i in range(min_length):
            chars = [n[i] for n in names]
            if chars.count(chars[0]) == len(chars):
                prefix_length += 1
            else:
                break

        for i in range(min_length):
            chars = [n[-i-1] for n in names]
            if chars.count(chars[0]) == len(chars):
                suffix_length += 1
            else:
                break

        #Make sure the suffix starts with uppercase
        #So we get eg. EquationsLumpingTypes.Unlumped and Lumped rather than Unl and L
        #And for the prefix so that TwoDim and ThreeDim don't become woDim and hreeDim
        #This breaks with a CMISS or CMISSCellML prefix for example though
        #
        #Constants will change to capitals with underscores soon so this won't be an issue then, we can just
        #check the prefix ends with an underscore
        if prefix_length > 0:
            prefix = names[0][0:prefix_length]
            if prefix == PREFIX:
                pass
            elif prefix == PREFIX+'CellML':
                pass
            else:
                while names[0][prefix_length-1].isupper():
                    prefix_length -= 1
        if suffix_length > 0:
            while names[0][-suffix_length].islower():
                suffix_length -= 1

    if suffix_length == 0:
        new_names = [name[prefix_length:] for name in names]
    else:
        new_names = [name[prefix_length:-suffix_length] for name in names]
    for (i,name) in enumerate(new_names):
        #Eg. NoOutputType should become None, not No
        if name == 'No':
            new_names[i] = 'NONE'
        elif name == 'None':
            #Can't assign to None
            new_names[i] = 'NONE'
        elif name[0].isdigit():
            new_names[i] = digit_to_word(name[0])+name[1:]
        elif name.endswith('VariableType'):
            # The NumberOfVariableSubtypes in this enum stuffs everything up
            new_names[i] = name[:-len('VariableType')]

    return new_names

def digit_to_word(digit):
    words = {
        0: 'Zero',
        1: 'One',
        2: 'Two',
        3: 'Three',
        4: 'Four',
        5: 'Five',
        6: 'Six',
        7: 'Seven',
        8: 'Eight',
        9: 'Nine'
    }
    return words[int(digit)]
