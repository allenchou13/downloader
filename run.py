import os
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Boolean
import subprocess
import threading
import time
import sanic
import sqlalchemy

data_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'data')
if not os.path.isdir(data_dir):
    os.makedirs(data_dir)

# echo=Ture----echo默认为False，表示不打印执行的SQL语句等较详细的执行信息，改为Ture表示让其打印。
# check_same_thread=False----sqlite默认建立的对象只能让建立该对象的线程使用，而sqlalchemy是多线程的所以我们需要
# 指定check_same_thread=False来让建立的对象任意线程都可使用。否则不时就会报错：sqlalchemy.exc.ProgrammingError: (
# sqlite3.ProgrammingError) SQLite objects created in a thread can only be used in that same thread. The object
# was created in thread id 35608 and this is thread id 34024. [SQL: 'SELECT users.id AS users_id, users.name AS
# users_name, users.fullname AS users_fullname, users.password AS users_password \nFROM users \nWHERE users.name
# = ?\n LIMIT ? OFFSET ?'] [parameters: [{}]] (Background on this error at: http://sqlalche.me/e/f405)
dl_db_file_path = os.path.join(data_dir, 'dl.db3')
engine = sqlalchemy.create_engine(
    f'sqlite:///{dl_db_file_path}', echo=False, connect_args={'check_same_thread': False})

Base = declarative_base()


class Task(Base):
    __tablename__ = 'tasks'

    id = Column(Integer, primary_key=True)
    url = Column(String(256))
    state = Column(String(20))
    filename = Column(String(128))

class Version(Base):
    __tablename__ = 'versions'
    id = Column(Integer, primary_key = True)
    major = Column(Integer)
    minor = Column(Integer)
    patch = Column(Integer)
    current = Column(Boolean)


Session = sessionmaker(bind=engine)

if not os.path.isfile(dl_db_file_path):
    Base.metadata.create_all(engine)
    session = Session()
    session.add(Version(major = 0, minor = 1, patch=1, current = True))
    session.commit()
    session.close()
else:
    session = Session()
    ver = session.query(Version).filter_by(current=True).first()
    while ver.major != 0 or ver.minor != 1 or ver.patch != 1:
        if ver.major == 0 and ver.minor == 1 and ver.patch == 0:
            ver.patch = 1
    session.commit()
    session.close()

files_dir = data_dir +'/files/'
for old_file in os.listdir():
    if os.path.isfile(files_dir + old_file):
        os.makedirs(files_dir + old_file + '_tmp')
        os.rename(files_dir + old_file, files_dir + old_file + '_tmp/' + old_file)
        os.rename(files_dir + old_file + '_tmp', files_dir + old_file)


def verify_state():
    session = Session()
    tsk_list = session.query(Task).filter_by(state='downloading')
    for tsk in tsk_list:
        tsk.state = 'created'
    
    tsk_list = session.query(Task).filter_by(state='compoleted')
    for tsk in tsk_list:
        tsk.state = 'completed'
    session.commit()
    session.close()


verify_state()


download_continue = True
def download():
    while download_continue:
        url = None
        tskid = -1
        session = Session()
        tsk = session.query(Task).filter_by(state='created').first()
        if tsk != None:
            tsk.state = 'downloading'
            url = tsk.url
            tskid = tsk.id
        session.commit()
        session.close()

        if url == None:
            time.sleep(1)
            continue

        print('downloading', url)
        dl_dir = os.path.join(data_dir, 'files', f'{tskid}')
        if not os.path.isdir(dl_dir):
            os.makedirs(dl_dir)
        else:
            files = os.listdir(dl_dir)
            for filename in files:
                print(f'delete file: {dl_dir}/{filename}')
                os.remove(os.path.join(dl_dir, filename))

        # subprocess.Popen(f'wget "{url}" --output-document ./{tskid}', shell=True, cwd=dl_dir)
        # subprocess.Popen(f'wget "{url}"', shell=True, cwd=dl_dir).wait()
        subprocess.Popen(f'curl -JLO "{url}"', shell=True, cwd=dl_dir).wait()

        session = Session()
        tsk = session.query(Task).filter_by(id=tskid).first()
        tsk.state = 'completed'
        session.commit()
        session.close()
        print('downloaded', url)


download_thread = threading.Thread(target=download)
download_thread.start()


app = sanic.Sanic(__name__)

app.static('/', 'static')


@app.route('/', methods=['GET'])
async def get_root(request):
    return sanic.response.redirect('./index.html')


@app.route('/tasks', methods=['GET'])
async def get_tasks(request):
    session = Session()
    tasks = session.query(Task)
    lst = []
    for tsk in tasks:
        lst.append({
            'id': tsk.id,
            'url': tsk.url,
            'state': tsk.state
        })
    return sanic.response.json(lst)


@app.route('/tasks', methods=['POST'])
async def add_task(request):
    url = request.json['url']
    tsk = Task(url=url, state="created")
    session = Session()
    session.add(tsk)
    session.commit()
    return sanic.response.text('OK')


@app.route('/tasks/<task_id:int>/file', methods=['GET'])
async def get_downlaoded_file(request, task_id):
    session = Session()
    tsk = session.query(Task).filter_by(id=task_id).first()
    if tsk == None:
        return sanic.response.text('', status=404)
    elif tsk.state != 'completed':
        return sanic.response.text('not completed')

    dl_dir = f'{data_dir}/files/{task_id}'
    files = os.listdir(dl_dir)
    if len(files) == 0:
        return sanic.response.text('', status=404)
    else:
        filename = files[0]
        file_content = open(dl_dir + '/' + filename, 'rb').read()
        return sanic.response.raw(file_content, headers={'Content-Disposition':f'attachment; filename="{filename}"'})


app.run(host='0.0.0.0', port=18000)

download_continue = False
download_thread.join()



