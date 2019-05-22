'''
Testing for the ApiJobQueue and related classes.
'''
import pytest

from queue import Queue
from sdclientapi import AuthError, RequestTimeoutError

from securedrop_client.queue import ApiInaccessibleError, ApiJob, RunnableQueue


def test_ApiInaccessibleError_init():
    # check default value
    err = ApiInaccessibleError()
    assert str(err).startswith('API is inaccessible')
    assert isinstance(err, Exception)

    # check custom
    msg = 'foo'
    err = ApiInaccessibleError(msg)
    assert str(err) == msg


def test_ApiJob_raises_NotImplemetedError():
    job = ApiJob()

    with pytest.raises(NotImplementedError):
        job.call_api(None, None)


def dummy_job_factory(mocker, return_value):
    '''
    Factory that creates dummy `ApiJob`s to DRY up test code.
    '''
    class DummyApiJob(ApiJob):
        success_signal = mocker.MagicMock()
        failure_signal = mocker.MagicMock()

        def __init__(self, *nargs, **kwargs):
            super().__init__(*nargs, **kwargs)
            self.return_value = return_value

        def call_api(self, api_client, session):
            if isinstance(self.return_value, Exception):
                raise self.return_value
            else:
                return self.return_value

    return DummyApiJob


def test_ApiJob_no_api(mocker):
    return_value = 'wat'
    api_job_cls = dummy_job_factory(mocker, return_value)
    api_job = api_job_cls()

    mock_session = mocker.MagicMock()

    with pytest.raises(ApiInaccessibleError):
        api_job._do_call_api(None, mock_session)

    assert not api_job.success_signal.emit.called
    assert not api_job.failure_signal.emit.called


def test_ApiJob_success(mocker):
    return_value = 'wat'
    api_job_cls = dummy_job_factory(mocker, return_value)
    api_job = api_job_cls()

    mock_api_client = mocker.MagicMock()
    mock_session = mocker.MagicMock()

    api_job._do_call_api(mock_api_client, mock_session)

    api_job.success_signal.emit.assert_called_once_with(return_value)
    assert not api_job.failure_signal.emit.called


def test_ApiJob_auth_error(mocker):
    return_value = AuthError('oh no')
    api_job_cls = dummy_job_factory(mocker, return_value)
    api_job = api_job_cls()

    mock_api_client = mocker.MagicMock()
    mock_session = mocker.MagicMock()

    with pytest.raises(ApiInaccessibleError):
        api_job._do_call_api(mock_api_client, mock_session)

    assert not api_job.success_signal.emit.called
    assert not api_job.failure_signal.emit.called


def test_ApiJob_timeout_error(mocker):
    return_value = RequestTimeoutError()
    api_job_cls = dummy_job_factory(mocker, return_value)
    api_job = api_job_cls()

    mock_api_client = mocker.MagicMock()
    mock_session = mocker.MagicMock()

    with pytest.raises(RequestTimeoutError):
        api_job._do_call_api(mock_api_client, mock_session)

    assert not api_job.success_signal.emit.called
    assert not api_job.failure_signal.emit.called


def test_ApiJob_other_error(mocker):
    return_value = Exception()
    api_job_cls = dummy_job_factory(mocker, return_value)
    api_job = api_job_cls()

    mock_api_client = mocker.MagicMock()
    mock_session = mocker.MagicMock()

    api_job._do_call_api(mock_api_client, mock_session)

    assert not api_job.success_signal.emit.called
    api_job.failure_signal.emit.assert_called_once_with(return_value)


def test_RunnableQueue_init(mocker):
    mock_api_client = mocker.MagicMock()
    mock_session_maker = mocker.MagicMock()

    queue = RunnableQueue(mock_api_client, mock_session_maker)
    assert queue.api_client == mock_api_client
    assert queue.session_maker == mock_session_maker
    assert isinstance(queue.queue, Queue)
    assert queue.queue.empty()
    assert queue.last_job is None


def test_RunnableQueue_happy_path(mocker):
    '''
    Add one job to the queue, run it.
    '''
    mock_process_events = mocker.patch('securedrop_client.queue.QApplication.processEvents')
    mock_api_client = mocker.MagicMock()
    mock_session = mocker.MagicMock()
    mock_session_maker = mocker.MagicMock(return_value=mock_session)
    return_value = 'foo'

    dummy_job_cls = dummy_job_factory(mocker, return_value)

    queue = RunnableQueue(mock_api_client, mock_session_maker)
    queue.queue.put_nowait(dummy_job_cls())

    queue._process(exit_loop=True)

    # this needs to be called at the end of the loop
    assert mock_process_events.called

    assert queue.last_job is None
    assert queue.queue.empty()


def test_RunnableQueue_job_timeout(mocker):
    '''
    Add two jobs to the queue. The first times out, and then gets "cached" for the next pass
    through the loop.
    '''
    mock_process_events = mocker.patch('securedrop_client.queue.QApplication.processEvents')
    mock_api_client = mocker.MagicMock()
    mock_session = mocker.MagicMock()
    mock_session_maker = mocker.MagicMock(return_value=mock_session)

    return_value = RequestTimeoutError()
    dummy_job_cls = dummy_job_factory(mocker, return_value)
    job1 = dummy_job_cls()
    job2 = dummy_job_cls()

    queue = RunnableQueue(mock_api_client, mock_session_maker)
    queue.queue.put_nowait(job1)
    queue.queue.put_nowait(job2)

    # attempt to process job1 knowing that it times out
    queue._process(exit_loop=True)

    # check that job1 is "cached" and a job is in the queue
    assert queue.last_job is job1
    assert queue.queue.qsize() == 1

    # update job1 to not raise an error so it can be processed
    job1.return_value = 'foo'

    # attempt to process the job1 again
    queue._process(exit_loop=True)

    # check that job has not been cached again
    assert queue.last_job is None
    assert queue.queue.qsize() == 1

    # attempt to process job2 knowing that it times out
    queue._process(exit_loop=True)

    # check that job2 was cached and that the queue is empty
    assert queue.last_job is job2
    assert queue.queue.empty()

    # ensure we don't have stale mocks
    assert mock_process_events.called
