#!/usr/bin/env python

__author__ = 'caipeichao'

import os
import sys
import json
import hjson
import urllib
import urllib.request
import difflib
import traceback
from collections import OrderedDict
import re


def main():
    # get argument
    if len(sys.argv) != 2:
        print_usage()
        exit(1)
        return
    test = sys.argv[1]

    # create test 05_suite
    test = JsonTest.create(test)

    # run test 05_suite
    reporter = ConsoleReporter()
    test.run(reporter)


def print_usage():
    print(u"""usage: ./jsontest.py <file|folder>""")


def create_test(path):
    """
    :param str path: A file or a folder contains test cases.
    :return: The JsonTest object according to path
    :rtype: JsonTest
    """
    path = os.path.realpath(path)
    if os.path.isfile(path):
        return TestFile(path)
    if os.path.isdir(path):
        return create_test_folder(path)
    raise Exception("Unknown file: " + path)


def create_test_folder(path):
    """
    :param str path: A folder contains test files.
    :return: The TestFolder according to path
    :rtype: TestFolder
    """
    path = os.path.realpath(path)
    return TestFolder(path)


class JsonTest:
    path = None

    @staticmethod
    def create(path):
        if os.path.isfile(path):
            return TestFile(path)
        if os.path.isdir(path):
            return TestFolder(path)
        raise Exception("Unknown file: " + path)


class TestFile(JsonTest):
    """
    A TestFile contains only one test case
    :type path str
    """

    def __init__(self, path):
        self.path = path

    def run(self, reporter):
        """
        Run one test case and report progress to reporter.
        :param TestReporter reporter: the reporter
        """
        # start to run test
        reporter.begin(self)

        # load test case. fail if load failed.
        try:
            test_case = self._load_test_case()
            test_case = self._evaluate_vars(test_case)
        except Exception as ex:
            log_error(ex)
            err = self._load_test_failed(ex)
            reporter.end(self, err)
            return err

        # if only test evaluation
        try:
            if self._is_evaluation_test():
                return self._run_evaluation_test(test_case)
        except Exception as ex:
            log_error(ex)
            err = self._run_test_failed(test_case, ex)
            reporter.end(self, err)
            return err

        # run test case. If failed, compare failure message.
        try:
            result = self._run_test_case(test_case)
        except Exception as ex:
            log_error(ex)
            err = self._run_test_failed(test_case, ex)
            reporter.end(self, err)
            return err

        # run test ok, report it
        reporter.end(self, result)
        return result

    def _is_evaluation_test(self):
        expect = self._get_evaluation_expect()
        if not expect:
            return False
        return True

    def _get_evaluation_expect(self):
        path = self.path + '.eval'
        if not os.path.exists(path):
            return None
        with open(path, 'rb') as f:
            return hjson.load(f, 'utf8')

    def _evaluate_vars(self, case):
        """
        :param dict|collections.OrderedDict case: a
        :return:
        :rtype: OrderedDict
        """
        # get vars from test case
        # is no vars, skip this step
        if not case: return case
        vars = case.get('var', None)
        if not vars: return case
        vars = self._json_clone(vars)

        # replace every vars
        result = self._evaluate_vars_dict(vars, case)
        return result

    def _evaluate_vars_dict(self, vars, case):
        """
        :param dict|OrderedDict vars: a
        :param dict|OrderedDict case: a
        :return:
        :rtype: OrderedDict
        """
        result = OrderedDict()
        for k, v in case.items():
            v = self._evaluate_vars_object(vars, v)
            result[k] = v
        return result

    def _evaluate_vars_object(self, vars, case):
        if type(case) == dict:
            return self._evaluate_vars_dict(vars, case)
        if type(case) == OrderedDict:
            return self._evaluate_vars_dict(vars, case)
        if type(case) == list:
            return self._evaluate_vars_list(vars, case)
        if type(case) == str:
            return self._evaluate_vars_str(vars, case)
        return case

    def _evaluate_vars_list(self, vars, case):
        result = []
        for e in case:
            e = self._evaluate_vars_object(vars, e)
            result.append(e)
        return result

    def _evaluate_vars_str(self, vars, s):
        # if the whole string is a replacement
        # should return var with type
        replace = lambda x: self._evaluate_vars_replace(vars, x)
        regex = r'\$\{([^}]*)\}'
        match = re.match(regex + '$', s)
        if match:
            return replace(match)

        # replace anything into string
        replace_str = lambda x: str(replace(x))
        return re.sub(regex, replace_str, s)

    def _evaluate_vars_replace(self, vars, m):
        """
        :param vars:
        :param re.__Match m: a
        :return:
        """
        # parse expression
        # eg. ${ <name> | <filter1> | <filter2> | ... }
        all = m.group(0)
        expression = m.group(1)
        name = expression.split('|')[0]
        filters = expression.split('|')[1:]

        # cannot find this var
        if name not in vars:
            raise Exception('Could not find var %s evaluating %s' % (name, all))

        # execute filters
        result = vars[name]
        if not filters:
            return result
        for e in filters:
            e = e.strip()
            if e == 'str':
                result = str(result)
            else:
                raise Exception("unknown filter %s evaluating %s" % (e, all))

        # replace ok
        return result


    def _load_test_case(self):
        """
        Load test case from self.path.
        If load failed then raise exception.
        Only dict is expected.
        :rtype: dict
        """
        try:
            return self._load_test_case_exception()
        except Exception as ex:
            log_error(ex)
            if 'Bad key name (eof)' in str(ex):
                return None

    def _load_test_case_exception(self):
        with open(self.path) as f:
            result = hjson.load(f, 'utf8')
            if not result:
                return None
            if type(result) not in [dict, OrderedDict]:
                raise Exception("Malformed test case, only dict is expected")
            return result

    def _load_test_failed(self, ex):
        """
        Return an TestResult for loading test failed.
        :param Exception ex: error during loading test
        :rtype: TestError
        """
        result = TestError()
        result.test = self
        result.passed = False
        result.message = 'Failed to load test: ' + repr(ex)
        return result

    def _run_evaluation_test(self, evaluated):
        # test nothing
        if evaluated is None:
            return

        # compare case with expect
        eval_expect = self._get_evaluation_expect()
        return self._generate_result(eval_expect, evaluated)

    def _run_test_case(self, case):
        """
        Make restful request according to the test case.
        Raise exception if error.
        :param dict case: the json of test case
        :rtype: TestFileResult
        """
        # test nothing
        if case is None:
            result = TestFileResult()
            result.passed = True
            result.test = self
            result.actual = None
            result.expect = None
            return result

        # make request
        response = self._make_request(case['request'])

        # compare result
        return self._generate_result_for_response(case, response)

    def _make_request(self, request):
        url = request['url']
        f = None
        try:
            f = urllib.request.urlopen(url)
            body = self._json_loads(f.read())
            if body is None:
                return dict()
            return {'body': body}
        except urllib.request.HTTPError as ex:
            log_error(ex)
            f = ex
            response = dict()
            response['status'] = str(f.code)
            body = self._json_loads(f.read())
            if body is None:
                return response
            response['body'] = body
            return response
        finally:
            if f:
                f.close()

    def _json_loads(self, bytes):
        s = bytes.decode('utf8')
        s = s.strip()
        if not s: return None
        return json.loads(s)

    def _filter_response(self, case):
        """
        Clone test case except response result.
        Used for compare result
        :param dict case: the test case
        :rtype: dict
        """
        result = OrderedDict()
        for k, v in case.items():
            if k == 'response':
                continue
            result[k] = v
        return result

    def _json_clone(self, j):
        return hjson.loads(hjson.dumps(j))

    def _run_test_failed(self, test_case, ex):
        """
        The test case is throwing exception
        :param dict test_case: the test case
        :param Exception ex: exception duration executing test case
        :rtype: TestFileResult
        """
        # response is exception
        response = {'error': repr(ex)}
        return self._generate_result_for_response(test_case, response)

    def _generate_result_for_response(self, case, response):
        # compare response
        actual = self._json_clone(case)
        actual = self._filter_response(actual)
        actual['response'] = response
        return self._generate_result(case, actual)

    def _generate_result(self, expect, actual):
        equals = JsonDiff(expect, actual).equals()

        # return result
        result = TestFileResult()
        result.passed = equals
        result.test = self
        result.expect = expect
        result.actual = actual
        return result


class TestFolder(JsonTest):
    """
    A TestFolder contains multiple TestFile or TestFolder
    :type path str
    :type tests list[JsonTest]
    """

    def __init__(self, path):
        self.path = path

    def run(self, reporter):
        """
        Run all sub tests in this folder
        """
        # start
        reporter.begin(self)

        # list all the files in folder
        try:
            files = os.listdir(self.path)
        except Exception as ex:
            log_error(ex)
            err = self._list_files_error(ex)
            reporter.end(self, err)
            return err

        # run every file
        result = TestFolderResult()
        result.passed = True
        result.test = self
        result.children = []
        for e in files:
            try:
                e = os.path.join(self.path, e)
                e = JsonTest.create(e)
                sub_result = e.run(reporter)
                result.children.append(sub_result)
            except Exception as ex:
                log_error(ex)
                err = self._run_test_case_error(ex, e)
                reporter.end(self, result)
                result.children.append(err)

        # run ok
        reporter.end(self, result)
        return result

    def _run_test_case_error(self, ex, case):
        """
        :param Exception ex: a
        :rtype: TestError
        """
        result = TestError()
        result.passed = False
        result.test = case
        result.message = repr(ex)
        return result

    def _list_files_error(self, ex):
        result = TestError()
        result.passed = False
        result.test = self
        result.message = repr(ex)
        return result


def log_error(ex):
    # traceback.print_exc()
    pass


class TestReporter:
    """
    A TestReporter receive testing progress and output a testing report
    after the tests finish.
    """

    def begin(self, test):
        """
        :param JsonTest test: The test is going to run
        :return: Nothing
        :rtype: NoneType
        """
        pass

    def end(self, test, result):
        """
        :param TestResult result: The test result
        :return: Nothing
        :rtype: NoneType
        """
        pass


class ConsoleReporter(TestReporter):
    def begin(self, test):
        pass

    def end(self, test, result):
        if result.passed:
            self.passed(test, result)
        else:
            self.failed(test, result)

    def passed(self, test, result):
        print('''Passed: %s''' % test.path)

    def failed(self, test, result):
        if type(result) == TestFolderResult:
            return self.failed_folder(test, result)
        if type(result) == TestFileResult:
            return self.failed_file(test, result)
        if type(result) == TestError:
            return self.failed_error(test, result)
        raise Exception("Unknown result type: " + str(type(result)))

    def failed_error(self, test, result):
        """
        :param test: a
        :param TestError result: a
        :return:
        """
        print('Error: %s' % test.path)
        print('Message: %s' % result.message)

    def failed_folder(self, test, result):
        """
        :param TestFolderResult result: a
        """
        print('Failed: %s' % test.path)

    def failed_file(self, test, result):
        """
        :param TestFileResult result: a
        """
        diff = JsonDiff(result.expect, result.actual).diff_text()
        print('''Failed: %s\n%s''' % (test.path, diff))


class TestResult:
    """
    The result of JsonTest.
    :type test JsonTest
    :type passed bool
    """
    test = None
    passed = None


class TestError(TestResult):
    """
    Test error from jsontest framework.
    :type message str
    """
    message = None


class TestFileResult(TestResult):
    """
    TestFileResult contains the diff between actual and expect.
    :type expect dict
    :type actual dict
    """
    expect = None
    actual = None


class JsonDiff:
    """
    A tool to compare jsons
    :type json1 dict
    :type json2 dict
    """

    def __init__(self, json1, json2):
        self.json1 = json1
        self.json2 = json2

    def equals(self):
        json1 = self._normalize_json(self.json1)
        json1 = json1.splitlines()
        json2 = self._normalize_json(self.json2)
        json2 = json2.splitlines()
        return json1 == json2

    def diff_text(self):
        json1 = self._normalize_json(self.json1)
        json1 = json1.splitlines()
        json2 = self._normalize_json(self.json2)
        json2 = json2.splitlines()
        d = difflib.Differ()
        diff = d.compare(json1, json2)
        return '\n'.join(diff) + '\n'

    def diff_html(self):
        """
        :param dict json1: a
        :param dict json2: a
        :return:
        :rtype: str
        """
        json1 = self._normalize_json(self.json1)
        json1 = json1.splitlines()
        json2 = self._normalize_json(self.json2)
        json2 = json2.splitlines()
        d = difflib.HtmlDiff()
        table = d.make_table(json1, json2)
        return table


    def _normalize_json(self, x):
        x = json.dumps(x)
        x = json.loads(x)
        x = self._normalize_object(x)
        x = json.dumps(x, indent=2, ensure_ascii=False)
        return x


    def _normalize_object(self, x):
        if type(x) == list:
            return self._normalize_list(x)
        elif type(x) == dict:
            return self._normalize_map(x)
        else:
            return x


    def _normalize_list(self, x):
        result = []
        for e in x:
            e = self._normalize_object(e)
            result.append(e)
        return result


    def _normalize_map(self, x):
        result = OrderedDict()
        for e in list(sorted(x)):
            result[e] = self._normalize_object(x[e])
        return result


class JsonDiffResult:
    table = None
    equals = None


class TestFolderResult(TestResult):
    def __init__(self):
        self.children = []


if __name__ == '__main__':
    main()