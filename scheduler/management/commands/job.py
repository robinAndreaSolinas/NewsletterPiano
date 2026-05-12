import inspect
from conf import settings
from django.core.management.base import BaseCommand
from scheduler.job_registry import JobRegistry
import logging

logging.disable(logging.WARNING)

class Command(BaseCommand):
    help = 'Base command to manage jobs'
    verbose_name = 'Job Manager'

    def add_arguments(self, parser):

        subparsers = parser.add_subparsers(dest='subcommand')

        list_parser = subparsers.add_parser('list', help='Elenca tutti i job registrati')
        list_parser.add_argument('--name', type=str, help='Filtra per nome')
        list_parser.add_argument('--trigger', type=str, help='Filtra per trigger')
        list_parser.add_argument('--hash', type=str, help='Filtra per id')
        list_parser.add_argument('-l', '--line-number', action='store_true', help='Mostra numero di riga', )

        execute = subparsers.add_parser('run', help='Esegui uno o più job')
        execute.add_argument('job', type=str, help='Hash, nome o pacchetto del job da eseguire', default=None, nargs='?')
        execute.add_argument('--all', action='store_true', help='Esegue tutti i job')
        execute.add_argument('-l', '--line-number', type=int, help='Esegue il job di una riga', )
        execute.add_argument('args', nargs='*', help='Positional arguments')


    def list_jobs(self, options, jobs):
        count = 0
        show_line = options.get('line_number')
        verbose = options.get('verbosity') != 1

        if not jobs:
            self.stderr.write("No jobs found")
            return

        # larghezza hash dinamica
        W = {
            'line': 4,
            'hash': max(max((len(j.id) if verbose else 8) for j in jobs) + 2, 20),
            'name': max(max(len(j.name) for j in jobs) + 2, 20),
            'trigger': max(max(len(j.trigger) for j in jobs) + 2, 20),
        }

        # header
        prefix = ''.ljust(W['line']) if show_line else ''
        self.stdout.write(
            f"{prefix}"
            f"{'HASH'.ljust(W['hash'])}"
            f"{'FUNCTION'.ljust(W['name'])}"
            f"{'TRIGGER'.ljust(W['trigger'])}"
            f"KWARGS"
        )

        for j in jobs:
            if ((options.get('name') and options['name'] not in j.name) or
                    (options.get('trigger') and options['trigger'] not in j.trigger) or
                    (options.get('hash') and options['hash'] not in j.id)):
                continue

            count += 1
            hash_str = j.id if verbose else j.id[:8]

            prefix = str(count).ljust(W['line']) if show_line else ''
            self.stdout.write(
                f"{prefix}"
                f"{hash_str.ljust(W['hash'])}"
                f"{j.name.ljust(W['name'])}"
                f"{j.trigger.ljust(W['trigger'])}"
                f"{j.kwargs}"
            )


    def run_job(self, options, jobs, *args, **kwargs):
        runner_job = set()

        if options['all']:
            for j in jobs:
                runner_job.add(j)
        elif options['job']:
            for j in jobs:
                if (
                    options['job'] == j.name
                    or options['job'][:8] == j.id[:8]
                    or options['job'] == j.id
                    or options['job'] == j.function.__module__.split(".")[0]
                ):
                    runner_job.add(j)

        elif options['line_number']:
            runner_job.add(list(jobs)[options['line_number'] - 1])

        if not runner_job:
            self.stderr.write("No jobs found")
            return


        try:
            self.stdout.write(f"Running job:")
            for j in runner_job:
                self.stdout.write(f" - <{j.name} {f'{j.id!r}' if options.get('verbosity') != 1 else f'{j.id[:8]!r}'}>")

                if (args or kwargs) and len(runner_job) == 1:
                    # if running only one job, pass args/kwargs to it
                    params = self._assign_params(j.function, *args, **kwargs)
                    j.function(**params)

                elif args or kwargs and len(runner_job) > 1:
                    raise TypeError

                else:
                    sched_args = j.kwargs.get('args', ())
                    sched_kwargs = j.kwargs.get('kwargs', {})
                    sig = inspect.signature(j.function)

                    required = [
                        p.name for p in sig.parameters.values()
                        if p.default is inspect.Parameter.empty
                           and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
                    ]

                    if sched_args or sched_kwargs:
                        # if there are scheduled args and kwargs, pass them to the job
                        j.function(*sched_args, **sched_kwargs)

                    elif not required:
                        # if there are no required args, run the job with his default values
                        j.function()

                    else:
                        raise TypeError(
                            f"Job '{j.name}' requires arguments: {', '.join(required)}\n"
                            f"Usage: manage.py job run {j.id[:8]} [arg|key=value] ..."
                        )
        except TypeError as e:
            self.stderr.write(
                "\nFailed to execute job: invalid arguments.\n"
                "Arguments can only be passed to a single job.\n"
                "Usage: manage.py job run <name|id> [arg|key=value] ..."
            )
            if settings.DEBUG:
                logging.exception(e)


    @staticmethod
    def _assign_params(fn, *args, **kwargs):

        sig = inspect.signature(fn)
        params = list(sig.parameters.keys())

        trimmed_args = []
        for i, val in enumerate(args):
            if i >= len(params) or params[i] in kwargs:
                break
            trimmed_args.append(val)

        bound_args = sig.bind_partial(*trimmed_args, **kwargs)
        bound_args.apply_defaults()
        return bound_args.arguments


    @staticmethod
    def split_args(arguments):
        a = ()
        kw = {}
        for arg in arguments:
            arg = arg.strip()
            if not arg or arg.startswith("-"):
                continue
            if "=" in arg:
                k, v = arg.split("=", 1)
                kw[k] = v
            else:
                a += (arg,)

        return a, kw


    def handle(self, *args, **options):

        jobs = JobRegistry.get()

        match options['subcommand']:

            case 'list':
                self.list_jobs(options, jobs)
            case 'run':
                fnargs, fnkwargs = self.split_args(args)

                self.run_job(options, jobs, *fnargs, **fnkwargs)
            case _:
                self.print_help('manage.py', 'job')