/* py2c.c — WeRDeep Build Wrapper
**
** Compile:
**   make -C src/wrapper/libft
**   gcc src/wrapper/py2c.c -Isrc -Lsrc/wrapper/libft -lft -o py2c
**
** Usage:
**   ./py2c <command> [options]
**
** Commands:
**   setup              Install system dependencies
**   build              Build and test locally
**   clean              Remove build artifacts
**   assembleRelease    Build optimized release binary
**   verify             Verify project structure is clean
**
** Note: Use CTRL+C to cancel an operation
*/

#include "libft/libft.h"
#include <dirent.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

int cmd_verify_inner(int strict);

#ifdef _WIN32
#define PSEP "\\"
#define EXE ".exe"
#include <direct.h>
#define mkdirp(path) _mkdir(path)
#else
#define PSEP "/"
#define EXE ""
#define mkdirp(path) mkdir(path, 0755)
#endif

#define BUF 4096
#define BIG 8192

#define QUIET  0
#define NORMAL 1
#define VERBOSE 2

#define TASK_COL 28

static char g_root[BUF];
static char g_build[BUF];
static char g_dist[BUF];
static char g_venv[BUF];
static int g_verbosity = NORMAL;
static int g_task_pending = 0;
static struct timeval g_task_start;

#define RED        "\033[0;31m"
#define GREEN      "\033[0;32m"
#define YELLOW     "\033[0;33m"
#define DIM        "\033[2m"
#define BOLD       "\033[1m"
#define BOLD_GREEN "\033[1;32m"
#define BOLD_RED   "\033[1;31m"
#define NC         "\033[0m"

static long elapsed_ms(struct timeval *start)
{
	struct timeval now;
	gettimeofday(&now, NULL);
	return (now.tv_sec - start->tv_sec) * 1000 + (now.tv_usec - start->tv_usec) / 1000;
}

static void task_result(const char *name, const char *status, const char *color)
{
	if (g_verbosity < NORMAL)
		return;
	long ms = 0;
	if (g_task_pending)
	{
		ms = elapsed_ms(&g_task_start);
		ft_putstr_fd("\033[A\033[2K\r", 1);
		g_task_pending = 0;
	}
	int len = ft_strlen((char *)name);
	ft_putstr_fd("> ", 1);
	ft_putstr_fd((char *)name, 1);
	int pad = TASK_COL - len - 2;
	while (pad-- > 0)
		ft_putchar_fd(' ', 1);
	ft_putstr_fd((char *)color, 1);
	ft_putstr_fd((char *)status, 1);
	ft_putstr_fd(NC, 1);
	if (ms > 0)
	{
		char timebuf[32];
		if (ms >= 60000)
			snprintf(timebuf, sizeof(timebuf), " (%ldm %lds)", ms / 60000, (ms % 60000) / 1000);
		else if (ms >= 1000)
			snprintf(timebuf, sizeof(timebuf), " (%lds)", ms / 1000);
		else
			snprintf(timebuf, sizeof(timebuf), " (%ldms)", ms);
		ft_putstr_fd(DIM, 1);
		ft_putstr_fd(timebuf, 1);
		ft_putstr_fd(NC, 1);
	}
	ft_putchar_fd('\n', 1);
}

static void task_running(const char *name)
{
	if (g_verbosity < NORMAL)
		return;
	gettimeofday(&g_task_start, NULL);
	int len = ft_strlen((char *)name);
	ft_putstr_fd("> ", 1);
	ft_putstr_fd((char *)name, 1);
	int pad = TASK_COL - len - 2;
	while (pad-- > 0)
		ft_putchar_fd(' ', 1);
	ft_putstr_fd(DIM "RUNNING" NC "\n", 1);
	g_task_pending = 1;
}

static void task_done(const char *name)
{
	task_result(name, "DONE", GREEN);
}

static void task_failed(const char *name)
{
	task_result(name, "FAILED", RED);
}

static void task_skipped(const char *name)
{
	task_result(name, "SKIPPED", YELLOW);
}

static void task_up_to_date(const char *name)
{
	task_result(name, "UP-TO-DATE", GREEN);
}

static void task_not_found(const char *name)
{
	task_result(name, "NOT FOUND", YELLOW);
}

static void task_pass(const char *name)
{
	task_result(name, "PASS", GREEN);
}

static void task_fail(const char *name)
{
	task_result(name, "FAIL", RED);
}

static void log_info(const char *msg)
{
	if (g_verbosity < NORMAL)
		return;
	ft_putstr_fd(DIM "  ", 1);
	ft_putendl_fd((char *)msg, 1);
	ft_putstr_fd(NC, 1);
}

static void log_error(const char *msg)
{
	if (g_verbosity < NORMAL)
		ft_putendl_fd((char *)msg, 2);
	else
	{
		ft_putstr_fd(RED "  " NC, 2);
		ft_putendl_fd((char *)msg, 2);
	}
}

static void log_warn(const char *msg)
{
	if (g_verbosity < NORMAL)
		return;
	ft_putstr_fd(YELLOW "  " NC, 2);
	ft_putendl_fd((char *)msg, 2);
}

static void build_result(int success, long ms)
{
	ft_putchar_fd('\n', 1);
	if (success)
	{
		ft_putstr_fd(BOLD_GREEN "BUILD SUCCESSFUL" NC, 1);
		if (ms > 0)
		{
			char buf[64];
			snprintf(buf, sizeof(buf), " in %lds", ms / 1000);
			ft_putstr_fd(buf, 1);
		}
		ft_putchar_fd('\n', 1);
	}
	else
	{
		ft_putstr_fd(BOLD_RED "BUILD FAILED" NC, 1);
		ft_putchar_fd('\n', 1);
	}
}

static char *path_join(const char *a, const char *b)
{
	char *sep = ft_strjoin(a, PSEP);
	char *full = ft_strjoin(sep, b);
	free(sep);
	return full;
}

static int run(const char *cmd)
{
	char *buf;

	if (g_verbosity >= VERBOSE)
	{
		ft_putstr_fd("  $ ", 1);
		ft_putendl_fd((char *)cmd, 1);
		return system(cmd);
	}
	buf = ft_strjoin(cmd, " >/dev/null 2>&1");
	int ret = system(buf);
	free(buf);
	return ret;
}

static int run_show(const char *cmd)
{
	if (g_verbosity >= VERBOSE)
	{
		ft_putstr_fd("  $ ", 1);
		ft_putendl_fd((char *)cmd, 1);
		return system(cmd);
	}
	char *buf = ft_strjoin(cmd, " >/dev/null 2>&1");
	int ret = system(buf);
	free(buf);
	return ret;
}

static int run_capture(const char *cmd, char *out, int outsize)
{
	FILE *fp = popen(cmd, "r");
	if (!fp)
		return -1;
	out[0] = '\0';
	size_t total = 0;
	char line[1024];
	while (fgets(line, sizeof(line), fp) && total < (size_t)(outsize - 1))
	{
		size_t len = ft_strlen(line);
		if (total + len >= (size_t)outsize)
			len = (size_t)outsize - total - 1;
		ft_memcpy(out + total, line, len);
		total += len;
	}
	out[total] = '\0';
	int ret = pclose(fp);
	char *trimmed = ft_strtrim(out, "\n\r ");
	if (trimmed)
	{
		ft_strlcpy(out, trimmed, outsize);
		free(trimmed);
	}
	return WEXITSTATUS(ret);
}

static int which(const char *cmd)
{
	char buf[BUF];
	snprintf(buf, BUF, "which %s >/dev/null 2>&1", cmd);
	return system(buf) == 0;
}

static int mkdirs(const char *path)
{
	char tmp[BUF];
	char *p;

	ft_strlcpy(tmp, path, BUF);
	for (p = tmp + 1; *p; p++)
	{
		if (*p == '/')
		{
			*p = '\0';
			mkdirp(tmp);
			*p = '/';
		}
	}
	mkdirp(tmp);
	return 0;
}

static int copy_file(const char *src, const char *dst)
{
	FILE *fsrc = fopen(src, "rb");
	if (!fsrc)
		return -1;
	FILE *fdst = fopen(dst, "wb");
	if (!fdst)
	{
		fclose(fsrc);
		return -1;
	}
	char buf[8192];
	size_t n;
	while ((n = fread(buf, 1, sizeof(buf), fsrc)) > 0)
		fwrite(buf, 1, n, fdst);
	fclose(fsrc);
	fclose(fdst);
	return 0;
}

static int rm_recursive(const char *path)
{
	char cmd[BUF];
	snprintf(cmd, BUF, "rm -rf %s", path);
	return system(cmd);
}

static int rm_pattern(const char *pattern)
{
	char cmd[BUF];
	snprintf(cmd, BUF, "rm -f %s", pattern);
	return system(cmd);
}

static void detect_root(const char *argv0)
{
	char cwd[BUF];
	if (getcwd(cwd, BUF))
	{
		char *check = path_join(cwd, "pyproject.toml");
		if (access(check, F_OK) == 0)
		{
			ft_strlcpy(g_root, cwd, BUF);
			free(check);
			return;
		}
		free(check);
	}
	char *dir = ft_strdup(argv0);
	if (!dir)
	{
		ft_strlcpy(g_root, ".", BUF);
		return;
	}
	char *slash = ft_strrchr(dir, '/');
	if (slash)
		*slash = '\0';
	else
		ft_strlcpy(dir, ".", BUF);
	char *check = path_join(dir, "pyproject.toml");
	if (access(check, F_OK) == 0)
		ft_strlcpy(g_root, dir, BUF);
	else
		ft_strlcpy(g_root, ".", BUF);
	free(dir);
	free(check);
}

static char *detect_python(void)
{
	if (which("python3"))
		return ft_strdup("python3");
	if (which("python"))
		return ft_strdup("python");
	return NULL;
}

static char *detect_python_ver(void)
{
	char *py = detect_python();
	if (!py)
		return NULL;
	char cmd[BUF];
	char ver[64];
	snprintf(cmd, BUF, "%s -c \"import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')\"", py);
	if (run_capture(cmd, ver, sizeof(ver)) != 0)
	{
		free(py);
		return NULL;
	}
	free(py);
	return ft_strdup(ver);
}

static const char *detect_platform(void)
{
#ifdef _WIN32
	return "windows";
#else
	char buf[64];
	run_capture("uname -s", buf, sizeof(buf));
	if (ft_strncmp(buf, "Linux", 5) == 0)
		return "linux";
	if (ft_strncmp(buf, "Darwin", 6) == 0)
		return "macos";
	return "unknown";
#endif
}

static const char *detect_arch(void)
{
#ifdef _WIN32
	return "x64";
#else
	char buf[64];
	run_capture("uname -m", buf, sizeof(buf));
	if (ft_strncmp(buf, "arm64", 5) == 0 || ft_strncmp(buf, "aarch64", 7) == 0)
		return "arm64";
	return "x64";
#endif
}

static int file_exists(const char *path)
{
	return access(path, F_OK) == 0;
}

static int dir_exists(const char *path)
{
	struct stat st;
	return stat(path, &st) == 0 && S_ISDIR(st.st_mode);
}

static int glob_exists(const char *pattern)
{
	char cmd[BUF];
	snprintf(cmd, BUF, "ls %s >/dev/null 2>&1", pattern);
	return system(cmd) == 0;
}

/* ================================================================ */
/* cmd_setup                                                        */
/* ================================================================ */

static int cmd_setup(void)
{
	int ok = 1;

	if (which("gcc") || which("cc"))
		task_done("C compiler");
	else
	{
		task_failed("C compiler");
		log_error("No C compiler (gcc or cc) found in PATH");
		ok = 0;
	}

	char *py = detect_python();
	if (py)
	{
		task_done("Python 3");
		free(py);
	}
	else
	{
		task_failed("Python 3");
		log_error("Python 3 not found in PATH");
		ok = 0;
	}

	if (which("cython"))
		task_done("Cython");
	else
	{
		task_not_found("Cython");
		log_warn("Install: pip install cython");
		ok = 0;
	}

	const char *plat = detect_platform();
	if (ft_strncmp(plat, "linux", 5) == 0)
	{
		if (which("patchelf"))
			task_done("patchelf");
		else
		{
			task_not_found("patchelf");
			log_warn("Install: sudo apt install patchelf");
		}
	}

	if (which("upx"))
		task_done("UPX");
	else
		task_not_found("UPX (optional)");

	char *libft_path = path_join(g_root, "src/wrapper/libft/libft.a");
	if (!file_exists(libft_path))
	{
		task_running("Build libft");
		char cmd[BUF];
		snprintf(cmd, BUF, "make -C %s/src/wrapper/libft", g_root);
		if (run(cmd) == 0)
			task_done("Build libft");
		else
		{
			task_failed("Build libft");
			ok = 0;
		}
	}
	else
		task_up_to_date("libft");
	free(libft_path);

	build_result(ok, 0);
	return ok ? 0 : 1;
}

/* ================================================================ */
/* cmd_build                                                        */
/* ================================================================ */

static int setup_venv(void)
{
	if (dir_exists(g_venv))
	{
		task_up_to_date("Virtual environment");
		return 0;
	}

	char cmd[BUF];
	char *py = detect_python();
	if (!py)
	{
		task_failed("Virtual environment");
		log_error("Python not found");
		return 1;
	}
	task_running("Virtual environment");
	snprintf(cmd, BUF, "%s -m venv %s", py, g_venv);
	free(py);
	if (run(cmd) != 0)
	{
		task_failed("Virtual environment");
		log_error("Failed to create virtual environment");
		return 1;
	}

	char *pip = path_join(g_venv, "bin/pip");
	snprintf(cmd, BUF, "%s install --upgrade pip wheel setuptools", pip);
	run(cmd);
	snprintf(cmd, BUF, "%s install cython types-requests certifi", pip);
	run(cmd);
	snprintf(cmd, BUF, "%s install -e %s", pip, g_root);
	run(cmd);

	if (file_exists(path_join(g_root, "requirements-build.txt")))
	{
		snprintf(cmd, BUF, "%s install -r %s/requirements-build.txt", pip, g_root);
		run(cmd);
	}
	free(pip);

	task_done("Virtual environment");
	return 0;
}

static int cython_ext(void)
{
	char cmd[BUF];
	char *py = path_join(g_venv, "bin/python");
	snprintf(cmd, BUF, "%s %s/setup.py build_ext --inplace", py, g_root);
	free(py);
	task_running("Cython extensions");
	if (run_show(cmd) != 0)
	{
		task_failed("Cython extensions");
		return 1;
	}
	task_done("Cython extensions");
	return 0;
}

static int run_lint(void)
{
	char cmd[BUF];
	snprintf(cmd, BUF, "%s/bin/pip show ruff >/dev/null 2>&1 || %s/bin/pip install --quiet ruff", g_venv, g_venv);
	run(cmd);
	snprintf(cmd, BUF, "%s/bin/ruff check %s/src/", g_venv, g_root);
	task_running("Lint");
	if (run_show(cmd) != 0)
	{
		task_failed("Lint");
		log_warn("Issues found (non-fatal)");
		return 0;
	}
	task_done("Lint");
	return 0;
}

static int run_typecheck(void)
{
	char cmd[BUF];
	snprintf(cmd, BUF, "%s/bin/pip show mypy >/dev/null 2>&1", g_venv);
	if (system(ft_strjoin(cmd, "")) != 0)
	{
		task_skipped("Type check");
		return 0;
	}
	snprintf(cmd, BUF, "%s/bin/mypy %s/src/werdeep --ignore-missing-imports", g_venv, g_root);
	task_running("Type check");
	if (run(cmd) != 0)
	{
		task_failed("Type check");
		log_warn("Issues found (non-fatal)");
	}
	else
		task_done("Type check");
	return 0;
}

static int run_tests(void)
{
	char cmd[BUF];
	snprintf(cmd, BUF, "%s/bin/pytest %s/tests/ -v --tb=short", g_venv, g_root);
	task_running("Tests");
	if (run_show(cmd) != 0)
	{
		task_failed("Tests");
		return 1;
	}
	task_done("Tests");
	return 0;
}

static void post_build_cleanup(void)
{
	char cmd[BUF];
	char *tmp;

	tmp = path_join(g_root, ".pytest_cache");
	rm_recursive(tmp);
	free(tmp);
	tmp = path_join(g_root, ".ruff_cache");
	rm_recursive(tmp);
	free(tmp);
	tmp = path_join(g_root, ".mypy_cache");
	rm_recursive(tmp);
	free(tmp);
	tmp = path_join(g_root, ".coverage");
	rm_recursive(tmp);
	free(tmp);
	tmp = path_join(g_root, "htmlcov");
	rm_recursive(tmp);
	free(tmp);
	tmp = path_join(g_root, "src/werdeep.egg-info");
	rm_recursive(tmp);
	free(tmp);
	snprintf(cmd, BUF, "find %s/src -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null", g_root);
	system(cmd);
	snprintf(cmd, BUF, "find %s/tests -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null", g_root);
	system(cmd);
}

static int cmd_build(void)
{
	struct timeval start;
	gettimeofday(&start, NULL);

	if (setup_venv() != 0)
	{
		build_result(0, elapsed_ms(&start));
		return 1;
	}

	if (cython_ext() != 0)
	{
		build_result(0, elapsed_ms(&start));
		return 1;
	}

	run_lint();
	run_typecheck();

	if (run_tests() != 0)
	{
		post_build_cleanup();
		build_result(0, elapsed_ms(&start));
		return 1;
	}

	post_build_cleanup();
	build_result(1, elapsed_ms(&start));
	if (g_verbosity >= NORMAL)
		log_info("Activate: source .build-venv/bin/activate");
	return 0;
}

/* ================================================================ */
/* cmd_clean                                                        */
/* ================================================================ */

static int cmd_clean(void)
{
	struct timeval start;
	gettimeofday(&start, NULL);

	task_running("Clean build artifacts");
	char *tmp;

	tmp = path_join(g_build, "main.c");
	rm_recursive(tmp);
	free(tmp);
	tmp = path_join(g_build, ".cython-error.log");
	rm_recursive(tmp);
	free(tmp);

	rm_recursive(g_dist);
	rm_recursive(g_venv);

	tmp = path_join(g_root, "src/werdeep.egg-info");
	rm_recursive(tmp);
	free(tmp);
	tmp = path_join(g_root, ".pytest_cache");
	rm_recursive(tmp);
	free(tmp);
	tmp = path_join(g_root, ".ruff_cache");
	rm_recursive(tmp);
	free(tmp);
	tmp = path_join(g_root, ".mypy_cache");
	rm_recursive(tmp);
	free(tmp);
	tmp = path_join(g_root, ".coverage");
	rm_recursive(tmp);
	free(tmp);
	tmp = path_join(g_root, "htmlcov");
	rm_recursive(tmp);
	free(tmp);

	char cmd[BIG];
	snprintf(cmd, BIG,
		"find %s/src/werdeep/engine -name '*.c' -not -name '__init__.c' -delete 2>/dev/null;"
		"find %s/src/werdeep/engine -name '*.so' -delete 2>/dev/null;"
		"find %s/src/werdeep/engine -name '*.html' -delete 2>/dev/null;"
		"find %s/src/werdeep/external -name '*.c' -not -name '__init__.c' -delete 2>/dev/null;"
		"find %s/src/werdeep/external -name '*.so' -delete 2>/dev/null;"
		"find %s/src/werdeep/external -name '*.html' -delete 2>/dev/null;"
		"find %s/src -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null;"
		"find %s/tests -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null",
		g_root, g_root, g_root, g_root, g_root, g_root, g_root, g_root);
	system(cmd);

	snprintf(cmd, BIG, "make -C %s/src/wrapper/libft fclean", g_root);
	run(cmd);

	task_done("Clean build artifacts");

	int vret = cmd_verify_inner(0);
	build_result(vret == 0, elapsed_ms(&start));
	return vret;
}

/* ================================================================ */
/* cmd_assembleRelease                                              */
/* ================================================================ */

struct release_opts
{
	char target[64];
	int build_all;
	int use_upx;
};

static int step_ensure_cython(void)
{
	if (which("cython"))
		return 0;
	char *vcy = path_join(g_venv, "bin/cython");
	if (file_exists(vcy))
	{
		free(vcy);
		return 0;
	}
	free(vcy);
	char cmd[BUF];
	if (dir_exists(g_venv))
	{
		char *pip = path_join(g_venv, "bin/pip");
		snprintf(cmd, BUF, "%s install cython", pip);
		free(pip);
	}
	else
	{
		char *py = detect_python();
		if (!py)
			return 1;
		snprintf(cmd, BUF, "%s -m pip install --user cython", py);
		free(py);
	}
	if (run(cmd) != 0)
		return 1;
	return 0;
}

static int step_cython_embed(void)
{
	char cmd[BIG];
	char *vcy = path_join(g_venv, "bin/cython");
	if (file_exists(vcy))
		snprintf(cmd, BIG, "%s %s/src/werdeep/cli/main.py --embed -o %s/main.c",
			vcy, g_root, g_build);
	else
		snprintf(cmd, BIG, "cython %s/src/werdeep/cli/main.py --embed -o %s/main.c",
			g_root, g_build);
	free(vcy);
	if (run(cmd) != 0)
		return 1;
	char sitepackages[BUF];
	snprintf(cmd, BUF,
		"%s/bin/python3 -c \"import site; print(site.getsitepackages()[0])\"",
		g_venv);
	if (run_capture(cmd, sitepackages, BUF) != 0)
		return 1;
	char wrap_path[BUF];
	snprintf(wrap_path, BUF, "%s/wrapper.c", g_build);
	FILE *fp = fopen(wrap_path, "w");
	if (!fp)
		return 1;
	fprintf(fp, "#include <stdlib.h>\n");
	fprintf(fp, "int __real_main(int argc, char **argv);\n");
	fprintf(fp, "int main(int argc, char **argv) {\n");
	fprintf(fp, "  setenv(\"PYTHONPATH\", \"%s/src:%s\", 1);\n", g_root, sitepackages);
	fprintf(fp, "  return __real_main(argc, argv);\n");
	fprintf(fp, "}\n");
	fclose(fp);
	snprintf(cmd, BIG,
		"sed -i '/^int$/N;s/^int\\nmain(/int __real_main(/;"
		"s/^int main(/int __real_main(/;"
		"s/^int wmain(/int __real_main(/' %s/main.c",
		g_build);
	if (system(cmd) != 0)
		return 1;
	return 0;
}

static int step_gcc_compile(const char *output_path)
{
	char *pyver = detect_python_ver();
	if (!pyver)
		return 1;

	const char *plat = detect_platform();
	char cmd[BIG];

	if (ft_strncmp(plat, "windows", 7) == 0)
	{
		char inc[BUF];
		char libdir[BUF];
		char py_cmd[BUF];
		char *py = detect_python();

		snprintf(py_cmd, BUF, "%s -c \"import sysconfig; print(sysconfig.get_path('include'))\"", py);
		run_capture(py_cmd, inc, BUF);

		snprintf(py_cmd, BUF, "%s -c \"import sys, os; print(os.path.join(sys.base_prefix, 'libs'))\"", py);
		run_capture(py_cmd, libdir, BUF);

		snprintf(cmd, BIG,
			"gcc -O2 %s/main.c %s/wrapper.c -mconsole -municode -I%s -L%s -lpython%s -o %s",
			g_build, g_build, inc, libdir, pyver, output_path);
		free(py);
	}
	else
	{
		char py_config[BUF];
		char cflags[BIG];
		char ldflags[BIG];
		int has_config = 0;

		snprintf(py_config, BUF, "python%s-config", pyver);
		if (which(py_config))
			has_config = 1;
		else if (which("python3-config"))
		{
			ft_strlcpy(py_config, "python3-config", BUF);
			has_config = 1;
		}

		if (!has_config)
		{
			free(pyver);
			return 1;
		}

		char cmd_cflags[BUF];
		snprintf(cmd_cflags, BUF, "%s --cflags", py_config);
		run_capture(cmd_cflags, cflags, BIG);

		char cmd_ldflags[BUF];
		snprintf(cmd_ldflags, BUF, "%s --ldflags", py_config);
		run_capture(cmd_ldflags, ldflags, BIG);

		const char *rpath = "";
		if (ft_strncmp(plat, "linux", 5) == 0)
			rpath = "-Wl,-rpath,'$ORIGIN'";

		const char *compiler = "gcc";
		if (ft_strncmp(plat, "macos", 5) == 0 && !which("gcc"))
			compiler = "cc";

		snprintf(cmd, BIG, "%s %s/main.c %s/wrapper.c %s %s -lpython%s %s -o %s",
			compiler, g_build, g_build, cflags, ldflags, pyver, rpath, output_path);
	}

	free(pyver);
	if (run_show(cmd) != 0)
		return 1;
	return 0;
}

static int step_strip(const char *binary)
{
	const char *plat = detect_platform();
	if (ft_strncmp(plat, "windows", 7) == 0)
		return 0;
	char cmd[BUF];
	snprintf(cmd, BUF, "strip %s", binary);
	if (run(cmd) != 0)
		return 1;
	return 0;
}

static int step_bundle_libpython(const char *dist_dir)
{
	const char *plat = detect_platform();
	char *pyver = detect_python_ver();
	if (!pyver)
		return 1;

	char cmd[BUF];
	char src[BUF];
	int ok = 1;

	if (ft_strncmp(plat, "linux", 5) == 0)
	{
		snprintf(cmd, BUF, "python3 -c \"import sysconfig; print(sysconfig.get_config_var('LIBDIR'))\"");
		char libdir[BUF];
		run_capture(cmd, libdir, BUF);
		snprintf(src, BUF, "%s/libpython%s.so.1.0", libdir, pyver);
		if (file_exists(src))
		{
			char *dst = path_join(dist_dir, ft_strjoin("libpython", ft_strjoin(pyver, ".so.1.0")));
			if (copy_file(src, dst) != 0)
				ok = 0;
			free(dst);
		}
		else
			ok = 0;
	}
	else if (ft_strncmp(plat, "macos", 5) == 0)
	{
		snprintf(cmd, BUF, "python3 -c \"import sysconfig; print(sysconfig.get_config_var('LIBDIR'))\"");
		char libdir[BUF];
		run_capture(cmd, libdir, BUF);
		snprintf(src, BUF, "%s/libpython%s.dylib", libdir, pyver);
		if (file_exists(src))
		{
			char *dst = path_join(dist_dir, ft_strjoin("libpython", ft_strjoin(pyver, ".dylib")));
			if (copy_file(src, dst) != 0)
				ok = 0;
			free(dst);
		}
		else
			ok = 0;
	}
	else if (ft_strncmp(plat, "windows", 7) == 0)
	{
		snprintf(cmd, BUF, "python -c \"import sys; print(sys.base_prefix)\"");
		char basedir[BUF];
		run_capture(cmd, basedir, BUF);
		snprintf(src, BUF, "%s\\python%s.dll", basedir, pyver);
		if (file_exists(src))
		{
			char *dst = path_join(dist_dir, ft_strjoin("python", ft_strjoin(pyver, ".dll")));
			if (copy_file(src, dst) != 0)
				ok = 0;
			free(dst);
		}
		else
			ok = 0;
	}

	free(pyver);
	return ok ? 0 : 1;
}

static int step_upx(const char *binary)
{
	if (!which("upx"))
		return 1;
	char cmd[BUF];
	snprintf(cmd, BUF, "upx --best --lzma %s", binary);
	if (run(cmd) != 0)
		return 1;
	return 0;
}

static int build_native(const char *target, const char *arch, int use_upx)
{
	char output_name[BUF];
	int is_windows = ft_strncmp(target, "windows", 7) == 0;

	snprintf(output_name, BUF, "werdeep-%s-%s%s", target, arch, is_windows ? ".exe" : "");

	char *release_path = path_join(g_root, "release");
	char *output_path = path_join(release_path, output_name);

	mkdirs(g_build);
	mkdirs(release_path);

	int failed = 0;

	task_running("Cython --embed");
	if (step_ensure_cython() != 0)
	{
		task_failed("Cython --embed");
		failed = 1;
	}
	else
	{
		if (step_cython_embed() != 0)
		{
			task_failed("Cython --embed");
			failed = 1;
		}
		else
			task_done("Cython --embed");
	}

	if (!failed)
	{
		task_running("GCC compile");
		if (step_gcc_compile(output_path) != 0)
		{
			task_failed("GCC compile");
			failed = 1;
		}
		else
			task_done("GCC compile");
	}

	if (!failed)
	{
		task_running("Strip symbols");
		if (step_strip(output_path) == 0)
			task_done("Strip symbols");
		else
			task_skipped("Strip symbols");
	}

	if (!failed && use_upx)
	{
		task_running("UPX compress");
		if (step_upx(output_path) == 0)
			task_done("UPX compress");
		else
			task_skipped("UPX compress");
	}

	if (!failed)
	{
		struct stat st;
		if (stat(output_path, &st) == 0)
		{
			char size_buf[64];
			long kb = st.st_size / 1024;
			if (kb > 1024)
				snprintf(size_buf, sizeof(size_buf), "%.1f MB", (double)kb / 1024.0);
			else
				snprintf(size_buf, sizeof(size_buf), "%ld KB", kb);
			char info[BUF];
			snprintf(info, BUF, "%s (%s)", output_path, size_buf);
			log_info(info);
		}
	}

	free(release_path);
	free(output_path);
	return failed ? 1 : 0;
}

static int try_docker_build(const char *target)
{
	if (!which("docker"))
	{
		task_skipped("Docker");
		log_warn("Docker not found -- cross-platform build skipped");
		return 1;
	}
	char cmd[BIG];
	snprintf(cmd, BIG,
		"docker build --platform linux/amd64 -t werdeep-builder -f %s/docker/Dockerfile.build %s && "
		"docker run --rm --platform linux/amd64 -v %s/release:/output werdeep-builder",
		g_root, g_root, g_root);
	return run(cmd) == 0 ? 0 : 1;
}

static int cmd_assembleRelease(int argc, char **argv)
{
	struct timeval start;
	gettimeofday(&start, NULL);

	struct release_opts opts;
	ft_strlcpy(opts.target, detect_platform(), sizeof(opts.target));
	opts.build_all = 0;
	opts.use_upx = 1;

	int i = 0;
	while (i < argc)
	{
		if (ft_strncmp(argv[i], "--target=", 9) == 0)
		{
			ft_strlcpy(opts.target, argv[i] + 9, sizeof(opts.target));
			i++;
		}
		else if (ft_strncmp(argv[i], "--target", 7) == 0 && i + 1 < argc)
		{
			ft_strlcpy(opts.target, argv[i + 1], sizeof(opts.target));
			i += 2;
		}
		else if (ft_strncmp(argv[i], "--all", 5) == 0)
		{
			opts.build_all = 1;
			i++;
		}
		else if (ft_strncmp(argv[i], "--no-upx", 8) == 0)
		{
			opts.use_upx = 0;
			i++;
		}
		else
			i++;
	}

	char *arch = ft_strdup(detect_arch());
	char target_clean[64];
	ft_strlcpy(target_clean, opts.target, sizeof(target_clean));

	if (ft_strncmp(target_clean, "macos-arm64", 11) == 0)
	{
		free(arch);
		arch = ft_strdup("arm64");
		ft_strlcpy(target_clean, "macos", sizeof(target_clean));
	}

	int ret;

	if (opts.build_all)
	{
		const char *native = detect_platform();
		const char *native_arch = detect_arch();
		ret = build_native(native, native_arch, opts.use_upx);
		if (ret == 0 && ft_strncmp(native, "linux", 5) != 0)
			try_docker_build("linux");
	}
	else
	{
		const char *native = detect_platform();
		if (ft_strncmp(target_clean, native, ft_strlen(native)) != 0)
			ret = try_docker_build(target_clean);
		else
			ret = build_native(target_clean, arch, opts.use_upx);
	}

	free(arch);
	build_result(ret == 0, elapsed_ms(&start));
	return ret;
}

/* ================================================================ */
/* cmd_verify                                                       */
/* ================================================================ */

static int check_not_exists(const char *desc, const char *pattern)
{
	char cmd[BUF];
	snprintf(cmd, BUF, "ls %s/%s >/dev/null 2>&1", g_root, pattern);
	if (system(cmd) == 0)
	{
		task_fail(desc);
		return 1;
	}
	return 0;
}

static int check_exists(const char *desc, const char *path)
{
	char *full = path_join(g_root, path);
	if (!file_exists(full))
	{
		task_fail(desc);
		free(full);
		return 1;
	}
	task_pass(desc);
	free(full);
	return 0;
}

int cmd_verify_inner(int strict)
{
	int failures = 0;

	if (strict)
	{
		failures += check_not_exists("Cython-generated .c", "src/werdeep/engine/*.c");
		failures += check_not_exists("Cython-generated .html", "src/werdeep/engine/*.html");
		failures += check_not_exists("Compiled .so extensions", "src/werdeep/engine/*.so");
		if (glob_exists("src/wrapper/libft/*.o") || glob_exists("src/wrapper/libft/*.a"))
		{
			task_fail("libft build artifacts");
			failures++;
		}
		else
			task_pass("libft build artifacts");
	}
	failures += check_not_exists("__pycache__ in src", "src/werdeep/**/__pycache__");
	failures += check_not_exists("__pycache__ in tests", "tests/**/__pycache__");
	failures += check_not_exists(".egg-info", "src/*.egg-info");
	failures += check_not_exists(".pytest_cache", ".pytest_cache");
	failures += check_not_exists(".ruff_cache", ".ruff_cache");
	failures += check_not_exists(".mypy_cache", ".mypy_cache");
	failures += check_not_exists(".coverage", ".coverage");
	failures += check_not_exists("htmlcov", "htmlcov");
	failures += check_not_exists("Stray .html at root", "*.html");
	failures += check_not_exists("pytest.ini", "pytest.ini");
	failures += check_not_exists("nuitka-hooks/", "nuitka-hooks");
	failures += check_not_exists("dist/ (use release/)", "dist");

	failures += check_exists("LICENSE", "LICENSE");
	failures += check_exists("pyproject.toml", "pyproject.toml");
	failures += check_exists("src/wrapper/py2c.c", "src/wrapper/py2c.c");

	return failures > 0 ? 1 : 0;
}

static int cmd_verify(int argc, char **argv)
{
	(void)argc;
	(void)argv;

	int strict = 0;
	int i = 0;
	while (argv && argv[i])
	{
		if (ft_strncmp(argv[i], "--strict", 8) == 0)
			strict = 1;
		i++;
	}

	int ret = cmd_verify_inner(strict);
	build_result(ret == 0, 0);
	return ret;
}

/* ================================================================ */
/* Usage & Main                                                     */
/* ================================================================ */

static void usage(void)
{
	ft_putstr_fd(
		"py2c - WeRDeep Build Wrapper\n"
		"\n"
		"Usage: ./py2c <command> [options]\n"
		"\n"
		"Commands:\n"
		"  setup                          Install system dependencies\n"
		"  build                          Build and test locally\n"
		"  clean                          Remove build artifacts\n"
		"  assembleRelease                Build optimized release binary\n"
		"  verify                         Verify project structure is clean\n"
		"\n"
		"Global Options:\n"
		"  --verbose, -v                  Show all output\n"
		"  --quiet, -q                    Only show build result\n"
		"\n"
		"assembleRelease Options:\n"
		"  --target=<platform>            linux, windows, macos, macos-arm64\n"
		"  --all                          Build for all platforms\n"
		"  --no-upx                       Skip UPX compression\n"
		"\n"
"verify Options:\n"
"  --strict                       Reject build artifacts (for CI)\n"
		"\n"
		"Examples:\n"
		"  ./py2c setup\n"
		"  ./py2c build\n"
		"  ./py2c verify\n"
		"  ./py2c assembleRelease --target=linux\n"
		"  ./py2c assembleRelease --no-upx --verbose\n"
		"\n"
		"Note: Use CTRL+C to cancel an operation\n",
		1);
}

int main(int argc, char **argv)
{
	int cmd_start = 1;
	int i = 1;
	while (i < argc)
	{
		if (ft_strncmp(argv[i], "--verbose", 9) == 0 || ft_strncmp(argv[i], "-v", 2) == 0)
		{
			g_verbosity = VERBOSE;
			cmd_start++;
			i++;
		}
		else if (ft_strncmp(argv[i], "--quiet", 7) == 0 || ft_strncmp(argv[i], "-q", 2) == 0)
		{
			g_verbosity = QUIET;
			cmd_start++;
			i++;
		}
		else
			break;
	}

	if (cmd_start >= argc)
	{
		ft_putstr_fd(BOLD_RED "BUILD FAILED" NC "\n", 2);
		ft_putstr_fd("  No command specified\n", 2);
		ft_putstr_fd("  Run: ./py2c --help\n", 2);
		return 1;
	}

	if (ft_strncmp(argv[cmd_start], "--help", 6) == 0 || ft_strncmp(argv[cmd_start], "-h", 2) == 0)
	{
		usage();
		return 0;
	}

	detect_root(argv[0]);
	snprintf(g_build, BUF, "%s/build", g_root);
	snprintf(g_dist, BUF, "%s/release", g_root);
	snprintf(g_venv, BUF, "%s/.build-venv", g_root);

	const char *cmd = argv[cmd_start];
	int sub_argc = argc - cmd_start - 1;
	char **sub_argv = sub_argc > 0 ? argv + cmd_start + 1 : NULL;

	if (ft_strncmp(cmd, "setup", 5) == 0)
		return cmd_setup();
	if (ft_strncmp(cmd, "build", 5) == 0)
		return cmd_build();
	if (ft_strncmp(cmd, "clean", 5) == 0)
		return cmd_clean();
	if (ft_strncmp(cmd, "assembleRelease", 15) == 0)
		return cmd_assembleRelease(sub_argc, sub_argv);
	if (ft_strncmp(cmd, "verify", 6) == 0)
		return cmd_verify(sub_argc, sub_argv);

	ft_putstr_fd(BOLD_RED "BUILD FAILED" NC "\n", 2);
	ft_putstr_fd("  Unknown command: ", 2);
	ft_putendl_fd((char *)cmd, 2);
	return 1;
}
