# Copyright 2019-2020 AstroLab Software
# Author: Julien Peloton
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import os
import glob
import doctest
import io
import json
import requests
from requests.exceptions import RequestException

from typing import Iterable
from typing import Any

from fastavro import reader, writer
import pandas as pd

import fastavro

from fink_client.tester import regular_unit_tests

class AlertReader():
    """ Class to load alert Avro files

    Parameters
    ----------
    path: str
        Path to alert Avro file or folder containing alert Avro files.

    Examples
    ----------
    Load a single Avro alert
    >>> r = AlertReader(avro_file)
    >>> list_of_alerts = r.to_list()
    >>> print(len(list_of_alerts))
    1

    Read a bunch of files
    >>> r = AlertReader(avro_folder)
    >>> df = r.to_pandas()
    >>> assert('objectId' in  df.columns)

    """
    def __init__(self, path: str):
        """ Initialise the AlertReader class """
        self.path = path
        self._load_avro_files()

    def _load_avro_files(self, ext_path: str = None):
        """ Load Avro alert data

        Parameters
        ----------
        ext_path: str, optional
            If not None, load explicitly data under `ext_path`.
            Default is None (self.path is used).
        """
        if ext_path is not None:
            path = ext_path
        else:
            path = self.path

        if os.path.isdir(path):
            self.filenames = glob.glob(os.path.join(path, '*.avro'))
        elif path == '':
            print('WARNING: path to avro files is empty')
            self.filenames = []
        elif fastavro.is_avro(path):
            self.filenames = [path]
        else:
            msg = """
            Data path not understood: {}
            You must give an avro file with
            its extension (.avro), or a folder with avro files.
            """.format(path)
            raise IOError(msg)

    def _read_single_alert(self, name: str = None) -> dict:
        """ Read an avro alert, and return data as dictionary

        Parameters
        ----------
        name: str, optional
            Name of the alert to read (avro format).
            Default is None (self.path is used).

        Returns
        ----------
        alert: dict
            Alert data in a dictionary

        Examples
        ----------
        >>> r = AlertReader("")
        WARNING: path to avro files is empty
        >>> alert = r._read_single_alert(name=avro_file)
        """
        if name is None:
            name = self.path

        with open(name, 'rb') as fo:
            avro_reader = reader(fo)

            # One alert per file only
            return avro_reader.next()

    def to_pandas(self) -> pd.DataFrame:
        """ Read Avro alert(s) and return data as Pandas DataFrame

        Returns
        ----------
        alert: pd.DataFrame
            Alert data in a pandas DataFrame

        Examples
        ----------
        >>> r = AlertReader(avro_folder)
        >>> df = r.to_pandas()
        >>> assert('objectId' in r.to_pandas().columns)

        """
        return pd.DataFrame(self.to_iterator())

    def to_list(self, size: int = None) -> list:
        """ Read Avro alert and return data as list of dictionary

        Returns
        ----------
        out: list of dictionary
            Alert data (dictionaries) in a list
        size: int, optional
            If not None, return only `size` alerts.
            Default is None.

        Examples
        ----------
        >>> r = AlertReader(avro_file)
        >>> mylist = r.to_list()
        >>> print(len(mylist))
        1

        >>> r = AlertReader(avro_folder)
        >>> mylist = r.to_list(size=2)
        >>> print(len(mylist))
        2
        """
        return [self._read_single_alert(fn) for fn in self.filenames[:size]]

    def to_iterator(self) -> Iterable[dict]:
        """ Return an iterator for alert data

        Returns
        ----------
        out: Iterable[dict]
            Alert data (dictionaries) in an iterator

        Examples
        ----------
        >>> r = AlertReader(avro_folder)
        >>> myiterator = r.to_iterator()
        >>> assert('objectId' in next(myiterator).keys())

        """
        for fn in self.filenames:
            yield self._read_single_alert(fn)

def write_alert(alert: dict, schema: str, path: str, overwrite: bool = False):
    """ Write avro alert on disk

    Parameters
    ----------
    alert: dict
        Alert data to save (dictionary with avro syntax)
    schema: str or dict
        Path to Avro schema of the alert, or parsed schema.
    path: str
        Folder that will contain the alert. The filename will always be
        <objectID>.avro

    Examples
    ----------
    >>> r = AlertReader(avro_file)
    >>> alert = r.to_list(size=1)[0]

    Write the alert on disk
    >>> write_alert(alert, schema_path, ".", overwrite=True)

    For test purposes, you can overwrite alert data on disk, but that should
    not happen in production as alert ID must be unique! Hence the writer will
    raise an exception if overwrite is not specified (default).
    >>> write_alert(
    ...     alert, schema_path, ".", overwrite=False)
    ... # doctest: +ELLIPSIS, +NORMALIZE_WHITESPACE
    Traceback (most recent call last):
      ...
    OSError: ./ZTF19acihgng.avro already exists!
    """
    alert_filename = os.path.join(path, "{}.avro".format(alert["objectId"]))

    if type(schema) == str:
        schema = _get_alert_schema(schema)
    # Check if the alert already exist
    if os.path.exists(alert_filename) and not overwrite:
        raise IOError("{} already exists!".format(alert_filename))

    with open(alert_filename, 'wb') as out:
        writer(out, schema, [alert])

def encode_into_avro(alert: dict, schema_file: str) -> str:
    """Encode a dict record into avro bytes

    Parameters
    ----------
    alert: dict
        A Dictionary of alert data
    schema_file: str
        Path of avro schema file

    Returns
    ----------
    value: str
        a bytes string with avro encoded alert data

    Examples
    ----------
    >>> r = AlertReader(avro_file)
    >>> alert = r.to_list(size=1)[0]
    >>> avro_encoded = encode_into_avro(alert, schema_path)
    """
    with open(schema_file) as f:
        schema = json.load(f)

    parsed_schema = fastavro.parse_schema(schema)
    b = io.BytesIO()
    fastavro.schemaless_writer(b, parsed_schema, alert)

    return b.getvalue()


def get_legal_topic_name(topic: str) -> str:
    """Returns a legal Kafka topic name

    Special characters are not allowed in the name
    of a Kafka topic. This method returns a legal name
    after removing special characters and converting each
    letter to lowercase

    Parameters
    ----------
    topic: str
        topic name, essentially an alert parameter which is to be used
        to create a topic

    Returns
    ----------
    legal_topic: str
        A topic name that can be used as a Kafka topic

    Examples
    ----------
    >>> bad_name = 'IaMEvi\\l'
    >>> good_name = get_legal_topic_name(bad_name)
    >>> print(good_name)
    iamevil
    """
    legal_topic = ''.join(a.lower() for a in topic if a.isalpha())
    return legal_topic

def _get_alert_schema(schema_path: str = None):
    """Returns schema for decoding avro alert

    This method downloads the latest schema available on the fink servers
    or falls back to using a default schema located in dir 'schemas'/

    Parameters
    ----------
    schema_path: str, optional
        a local path where to look for schema,
        Note that schema doesn't get downloaded from fink servers if schema_path
        is given

    Returns
    ----------
    parsed_schema: dict
        Dictionary of json format schema for decoding avro alerts from fink
    """
    if schema_path is None:
        # get schema from fink-broker
        try:
            print("Getting schema from fink servers...")
            schema_url = "https://raw.github.com/astrolabsoftware/fink-broker/master/schemas/distribution_schema_0p2.avsc"
            filename = schema_url.split("/")[-1]
            r = requests.get(schema_url, timeout=1)
            schema_path = os.path.abspath(os.path.join(
                os.path.dirname(__file__), '../schemas/{}'.format(filename)))
            with open(schema_path, "w") as f:
                f.write(r.text)
        except RequestException:
            schema_path = os.path.abspath(
                os.path.join(
                    os.path.dirname(__file__),
                    '../schemas/distribution_schema_0p2.avsc'
                )
            )

            msg = """
            Could not obtain schema from fink servers
            Using default schema available at: {}
            """.format(schema_path)
            print(msg)

    with open(schema_path) as f:
        schema = json.load(f)

    return fastavro.parse_schema(schema)

def _decode_avro_alert(avro_alert: io.IOBase, schema: dict) -> Any:
    """Decodes a file-like stream of avro data

    Parameters
    ----------
    avro_alert: io.IOBase
        a file-like stream with avro encoded data

    schema: dict
        Dictionary of json format schema to decode avro data

    Returns
    ----------
    record: Any
        Record obtained after decoding avro data (typically, dict)
    """
    avro_alert.seek(0)
    return fastavro.schemaless_reader(avro_alert, schema)


if __name__ == "__main__":
    """ Run the test suite """

    args = globals()
    args['avro_file'] = 'datatest/ZTF19acihgng.avro'
    args['avro_folder'] = 'datatest'
    args['schema_path'] = 'schemas/distribution_schema_0p2.avsc'

    regular_unit_tests(global_args=args)
