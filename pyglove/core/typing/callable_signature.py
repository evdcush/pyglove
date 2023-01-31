# Copyright 2023 The PyGlove Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Callable signatures based on PyGlove typing."""

import dataclasses
import enum
import inspect
import typing
from typing import Any, Callable, Dict, List, Optional

from pyglove.core import object_utils
from pyglove.core.typing import class_schema


@dataclasses.dataclass
class Argument:
  """Definition for a callable argument."""
  name: str
  value_spec: class_schema.ValueSpec

  @classmethod
  def from_annotation(
      cls,
      name: str,
      annotation: Any = inspect.Parameter.empty):
    """Creates an argument from annotation."""
    return Argument(
        name, class_schema.ValueSpec.from_annotation(annotation)
    )


class CallableType(enum.Enum):
  """Enum for Callable type."""
  # Regular function or lambdas without a subject bound.
  FUNCTION = 1

  # Function that is bound with subject. Like class methods or instance methods.
  METHOD = 2


class Signature(object_utils.Formattable):
  """PY3 function signature."""

  def __init__(self,
               callable_type: CallableType,
               name: str,
               module_name: str,
               args: Optional[List[Argument]] = None,
               kwonlyargs: Optional[List[Argument]] = None,
               varargs: Optional[Argument] = None,
               varkw: Optional[Argument] = None,
               return_value: Optional[class_schema.ValueSpec] = None,
               qualname: Optional[str] = None):
    """Constructor.

    Args:
      callable_type: Type of callable.
      name: Function name.
      module_name: Module name.
      args: Specification for positional arguments
      kwonlyargs: Specification for keyword only arguments (PY3).
      varargs: Specification for wildcard list argument, e.g, 'args' is the name
        for `*args`.
      varkw: Specification for wildcard keyword argument, e.g, 'kwargs' is the
        name for `**kwargs`.
      return_value: Optional value spec for return value.
      qualname: Optional qualified name.
    """
    args = args or []
    self.callable_type = callable_type
    self.name = name
    self.module_name = module_name
    self.args = args or []
    self.kwonlyargs = kwonlyargs or []
    self.varargs = varargs
    self.varkw = varkw
    self.return_value = return_value
    self.qualname = qualname or name

  @property
  def named_args(self):
    """Returns all named arguments according to their declaration order."""
    return self.args + self.kwonlyargs

  @property
  def arg_names(self):
    """Returns names of all arguments according to their declaration order."""
    return [arg.name for arg in self.named_args]

  def get_value_spec(self, name: str) -> Optional[class_schema.ValueSpec]:
    """Returns Value spec for an argument name.

    Args:
      name: Argument name.

    Returns:
      ValueSpec for the requested argument. If name is not found, value spec of
      wildcard keyword argument will be used. None will be returned if name
      does not exist in signature and wildcard keyword is not accepted.
    """
    for arg in self.named_args:
      if arg.name == name:
        return arg.value_spec
    if self.has_varkw:
      return self.varkw.value_spec
    return None

  @property
  def id(self) -> str:
    """Returns ID of the function."""
    return f'{self.module_name}.{self.qualname}'

  @property
  def has_varargs(self) -> bool:
    """Returns whether wildcard positional argument is present."""
    return self.varargs is not None

  @property
  def has_varkw(self) -> bool:
    """Returns whether wildcard keyword argument is present."""
    return self.varkw is not None

  @property
  def has_wildcard_args(self) -> bool:
    """Returns whether any wildcard arguments are present."""
    return self.has_varargs or self.has_varkw

  def __ne__(self, other: Any) -> bool:
    """Not equals."""
    return not self.__eq__(other)

  def __eq__(self, other: Any) -> bool:
    """Equals."""
    if not isinstance(other, self.__class__):
      return False
    if self is other:
      return True
    return (self.callable_type == other.callable_type and
            self.name == other.name and
            self.qualname == other.qualname and
            self.module_name == other.module_name and
            self.args == other.args and self.kwonlyargs == other.kwonlyargs and
            self.varargs == other.varargs and self.varkw == other.varkw and
            self.return_value == other.return_value)

  def format(self, *args, **kwargs) -> str:
    """Format current object."""
    details = object_utils.kvlist_str([
        ('', repr(self.id), ''),
        ('args', object_utils.format(self.args, **kwargs), '[]'),
        ('kwonlyargs', object_utils.format(self.kwonlyargs, **kwargs), '[]'),
        ('returns', object_utils.format(self.return_value, **kwargs), 'None'),
        ('varargs', object_utils.format(self.varargs, **kwargs), 'None'),
        ('varkw', object_utils.format(self.varkw, **kwargs), 'None'),
    ])
    return f'{self.__class__.__name__}({details})'

  @classmethod
  def from_callable(cls, callable_object: Callable) -> 'Signature':  # pylint: disable=g-bare-generic
    """Creates Signature from a callable object."""
    callable_object = typing.cast(object, callable_object)
    if not callable(callable_object):
      raise TypeError(f'{callable_object!r} is not callable.')

    if isinstance(callable_object, object_utils.Functor):
      assert callable_object.signature is not None
      return callable_object.signature

    func = callable_object
    if not inspect.isroutine(func):
      if not inspect.isroutine(callable_object.__call__):
        raise TypeError(f'{callable_object!r}.__call__ is not a method.')
      func = callable_object.__call__

    def get_value_spec(param: inspect.Parameter) -> class_schema.ValueSpec:
      if param.default != inspect.Parameter.empty:
        return class_schema.ValueSpec.from_annotation(
            param.default, True
        ).set_default(param.default)
      elif param.annotation != inspect.Parameter.empty:
        return class_schema.ValueSpec.from_annotation(param.annotation, True)
      else:
        return class_schema.ValueSpec.from_annotation(param.annotation)

    def make_arg_spec(param: inspect.Parameter) -> Argument:
      return Argument(param.name, get_value_spec(param))

    sig = inspect.signature(func)
    args = []
    kwonly_args = []
    varargs = None
    varkw = None

    for param in sig.parameters.values():
      arg_spec = make_arg_spec(param)
      if (param.kind == inspect.Parameter.POSITIONAL_ONLY
          or param.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD):
        args.append(arg_spec)
      elif param.kind == inspect.Parameter.KEYWORD_ONLY:
        kwonly_args.append(arg_spec)
      elif param.kind == inspect.Parameter.VAR_POSITIONAL:
        varargs = arg_spec
      else:
        assert param.kind == inspect.Parameter.VAR_KEYWORD, param.kind
        varkw = arg_spec

    if inspect.ismethod(func):
      callable_type = CallableType.METHOD
    else:
      callable_type = CallableType.FUNCTION

    return Signature(
        callable_type=callable_type,
        name=func.__name__,
        module_name=getattr(func, '__module__', 'wrapper'),
        qualname=func.__qualname__,
        args=args, kwonlyargs=kwonly_args, varargs=varargs, varkw=varkw)

  def make_function(
      self,
      body: List[str],
      exec_globals: Optional[Dict[str, Any]] = None,
      exec_locals: Optional[Dict[str, Any]] = None):
    """Makes a function with current signature."""
    if exec_globals is None:
      exec_globals = {}
    if exec_locals is None:
      exec_locals = {}

    args = []
    def _append_arg(
        arg_name: str,
        arg_spec: class_schema.ValueSpec,
        force_missing_as_default: bool = False,
        arg_prefix: str = ''):
      s = [f'{arg_prefix}{arg_name}']
      if arg_spec.annotation != object_utils.MISSING_VALUE:
        s.append(f': _annotation_{arg_name}')
        exec_locals[f'_annotation_{arg_name}'] = arg_spec.annotation
      if not arg_prefix and (force_missing_as_default or arg_spec.has_default):
        s.append(f' = _default_{arg_name}')
        exec_locals[f'_default_{arg_name}'] = arg_spec.default
      args.append(''.join(s))

    has_previous_default = False
    # Build positional arguments.
    for arg in self.args:
      _append_arg(arg.name, arg.value_spec, has_previous_default)
      if arg.value_spec.has_default:
        has_previous_default = True

    # Build variable positional arguments.
    if self.varargs:
      _append_arg(self.varargs.name, self.varargs.value_spec, arg_prefix='*')
    elif self.kwonlyargs:
      args.append('*')

    # Build keyword-only arguments.
    for arg in self.kwonlyargs:
      _append_arg(arg.name, arg.value_spec)

    # Build variable keyword arguments.
    if self.varkw:
      _append_arg(self.varkw.name, self.varkw.value_spec, arg_prefix='**')

    # Generate function.
    fn = object_utils.make_function(
        self.name,
        args=args,
        body=body,
        exec_globals=exec_globals,
        exec_locals=exec_locals,
        return_type=self.return_value or object_utils.MISSING_VALUE)
    fn.__module__ = self.module_name
    fn.__name__ = self.name
    fn.__qualname__ = self.qualname
    return fn


def get_signature(func: Callable) -> Signature:  # pylint:disable=g-bare-generic
  """Gets signature from a python callable."""
  return Signature.from_callable(func)
